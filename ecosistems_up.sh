#!/usr/bin/env bash
# =============================================================================
# ecosistems_up.sh — Arranque por fases del AI Ecosystem
#
# Uso:
#   ./ecosistems_up.sh              # arranca en modo dev (por defecto)
#   ./ecosistems_up.sh prod         # arranca en modo prod (incluye Traefik)
#
# Flags opcionales:
#   --skip-observability   omite OpenSearch + OTEL Collector
#   --skip-ui              omite todos los paneles web
#   --only-infra           arranca solo Fase 1 (bases de datos + brokers)
# =============================================================================

set -euo pipefail

# ─── Colores ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()     { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }
success() { echo -e "${GREEN}[$(date +%H:%M:%S)] ✓${NC} $*"; }
warn()    { echo -e "${YELLOW}[$(date +%H:%M:%S)] ⚠${NC}  $*"; }
error()   { echo -e "${RED}[$(date +%H:%M:%S)] ✗${NC} $*"; exit 1; }
phase()   { echo -e "\n${BOLD}${CYAN}━━━ $* ━━━${NC}\n"; }

# ─── Argumentos ─────────────────────────────────────────────────────────────
PROFILE="${1:-dev}"
SKIP_OBSERVABILITY=false
SKIP_UI=false
ONLY_INFRA=false

for arg in "$@"; do
  case $arg in
    --skip-observability) SKIP_OBSERVABILITY=true ;;
    --skip-ui)            SKIP_UI=true ;;
    --only-infra)         ONLY_INFRA=true ;;
  esac
done

[[ "$PROFILE" != "dev" && "$PROFILE" != "prod" ]] && \
  error "Perfil inválido: '$PROFILE'. Usa 'dev' o 'prod'."

DC="docker compose"
DC_PROFILE="$DC --profile $PROFILE"

# Nombre del proyecto — debe coincidir con name: en docker-compose.yml
COMPOSE_PROJECT="ai-ecosystem"

# Mapa service → container_name (según container_name: en el compose)
declare -A CONTAINER_NAME=(
  [postgres]="ai_postgres"
  [redis]="ai_cache"
  [rabbitmq]="ai_broker"
  [minio]="ai_blob_storage"
  [weaviate]="ai_vector_db"
  [clickhouse]="ai_observability_db"
  [opensearch]="ai_logs_db"
  [langfuse-server]="ai_observability"
  [langfuse-worker]="ai_observability_worker"
  [n8n]="ai_orchestrator"
  [evolution]="ai_evolution"
  [webchat-gateway]="ai_webchat_gateway"
  [otel-collector]="ai_collector"
  [redis-insight]="ai_redis_ui"
  [rabbitmq-scout]="ai_broker_ui"
  [weaviate-gui]="ai_vector_ui"
  [opensearch-dashboards]="ai_logs_ui"
  [traefik]="ai_traefik"
)

# ─── Helpers ─────────────────────────────────────────────────────────────────

# Devuelve el ID del contenedor. Estrategia en cascada:
# 1. Por container_name explícito (más directo y fiable)
# 2. Via compose ps con profile
# 3. Via labels Docker Compose
_get_container_id() {
  local service="$1"
  local cid=""

  local cname="${CONTAINER_NAME[$service]:-}"
  if [[ -n "$cname" ]]; then
    cid=$(docker ps -q --filter "name=^${cname}$" 2>/dev/null | head -1) || true
    [[ -n "$cid" ]] && echo "$cid" && return 0
  fi

  cid=$($DC_PROFILE ps -q "$service" 2>/dev/null | head -1) || true
  [[ -n "$cid" ]] && echo "$cid" && return 0

  cid=$(docker ps -q \
    --filter "label=com.docker.compose.service=$service" \
    --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
    2>/dev/null | head -1) || true
  [[ -n "$cid" ]] && echo "$cid" && return 0

  return 1
}

# Espera a que un contenedor pase a estado "healthy"
wait_healthy() {
  local service="$1"
  local timeout="${2:-180}"
  local container=""

  local resolve_elapsed=0
  while [[ -z "$container" ]] && (( resolve_elapsed < 20 )); do
    container=$(_get_container_id "$service") || true
    if [[ -z "$container" ]]; then
      sleep 4
      (( resolve_elapsed += 4 ))
    fi
  done

  if [[ -z "$container" ]]; then
    warn "No se encontró el contenedor de '$service' tras ${resolve_elapsed}s, saltando espera."
    return 0
  fi

  log "Esperando a que '$service' esté healthy (máx. ${timeout}s)…"
  local elapsed=0

  while true; do
    local status
    status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "unknown")

    case "$status" in
      healthy)
        success "'$service' está healthy."
        return 0
        ;;
      unhealthy)
        if (( elapsed < 60 )); then
          warn "'$service' unhealthy a los ${elapsed}s — puede ser transitorio, reintentando…"
        else
          echo ""
          warn "Health log de '$service':"
          docker inspect --format='{{range .State.Health.Log}}  [exit={{.ExitCode}}] {{.Output}}{{end}}' \
            "$container" 2>/dev/null | tail -5 || true
          error "'$service' UNHEALTHY definitivo. Ver logs: docker logs ${CONTAINER_NAME[$service]:-$container}"
        fi
        ;;
      "no healthcheck")
        warn "'$service' no tiene healthcheck definido, continuando…"
        return 0
        ;;
    esac

    if (( elapsed >= timeout )); then
      echo ""
      error "Timeout esperando '$service' después de ${timeout}s (estado: $status)"
    fi

    sleep 5
    (( elapsed += 5 ))
    echo -ne "  ${YELLOW}…${NC} ${elapsed}s / ${timeout}s\r"
  done
}

# ─── Verificaciones previas ──────────────────────────────────────────────────
phase "Verificaciones previas"

command -v docker >/dev/null 2>&1 || error "Docker no encontrado."
docker info >/dev/null 2>&1       || error "El daemon de Docker no está corriendo."

[[ -f ".env" ]] || error "No se encontró .env en el directorio actual."

# Carga las variables del .env para usarlas en este script (ej: bloque MinIO)
set -a
# shellcheck disable=SC1091
source .env
set +a

log "Perfil activo    : ${BOLD}$PROFILE${NC}"
log "Proyecto Compose : ${BOLD}$COMPOSE_PROJECT${NC}"
$SKIP_OBSERVABILITY && warn "--skip-observability: se omiten OpenSearch y OTEL Collector."
$SKIP_UI            && warn "--skip-ui: se omiten los paneles web."
$ONLY_INFRA         && warn "--only-infra: se arranca solo la infraestructura base."

# ─── FASE 1a: Postgres y Redis (fundación) ────────────────────────────────────
phase "Fase 1a — Fundación (postgres + redis)"

$DC_PROFILE up -d --remove-orphans --no-deps postgres redis
wait_healthy postgres 300
wait_healthy redis 120

success "Postgres y Redis están healthy."

# ─── FASE 1b: Infraestructura pesada (uno a uno para no saturar Docker Desktop) ─
phase "Fase 1b — Infraestructura pesada (rabbitmq → minio → weaviate → clickhouse)"

for svc in rabbitmq minio weaviate clickhouse; do
  log "Arrancando $svc…"
  $DC_PROFILE up -d --remove-orphans --no-deps "$svc"
  wait_healthy "$svc" 300
done

success "Infraestructura base completa."

# ─── FASE 2: Bucket MinIO + OpenSearch ───────────────────────────────────────
phase "Fase 2 — Init bucket MinIO y observabilidad de logs"

# Crea el bucket de MinIO usando minio/mc como contenedor temporal.
# minio/mc no tiene sh — cada comando va en su propio docker run.
# Compartimos el config dir via volumen Docker temporal para que el alias
# configurado en el primer run esté disponible en el segundo.
log "Creando bucket MinIO '${MINIO_BUCKET}'…"

MC_VOL="mc_config_$$"
docker volume create "$MC_VOL" > /dev/null

# 1. Configura el alias (escribe en el volumen compartido)
docker run --rm \
  --network "${COMPOSE_PROJECT}_backend_network" \
  -v "${MC_VOL}:/root/.mc" \
  minio/mc alias set local \
    "http://minio:${MINIO_PORT}" \
    "${MINIO_ROOT_USER}" \
    "${MINIO_ROOT_PASSWORD}" \
    --quiet

# 2. Crea el bucket — distingue "ya existe" de error real
BUCKET_OUTPUT=$(docker run --rm \
  --network "${COMPOSE_PROJECT}_backend_network" \
  -v "${MC_VOL}:/root/.mc" \
  minio/mc mb "local/${MINIO_BUCKET}" 2>&1) && \
  success "Bucket '${MINIO_BUCKET}' creado." || {
    if echo "$BUCKET_OUTPUT" | grep -qiE "already (exists|owned|your bucket)"; then
      success "Bucket '${MINIO_BUCKET}' ya existe — sin cambios."
    else
      warn "Error al crear el bucket: $BUCKET_OUTPUT"
    fi
  }

docker volume rm "$MC_VOL" > /dev/null

$ONLY_INFRA && { success "Modo --only-infra: finalizado."; exit 0; }

if ! $SKIP_OBSERVABILITY; then
  log "Arrancando OpenSearch (puede tardar 2-3 min en primer boot)…"
  $DC_PROFILE up -d --remove-orphans --no-deps opensearch
  log "Esperando a que OpenSearch arranque (60s)…"
  sleep 60
  log "Verificando OpenSearch…"
  docker exec ai_logs_db curl -sf --max-time 5 \
    -ku "admin:${OPENSEARCH_PASSWORD}" \
    https://localhost:9200/_cluster/health 2>/dev/null | grep -q status \
    && success "OpenSearch está respondiendo." \
    || warn "OpenSearch no responde aún — continuando de todas formas."
fi

# ─── FASE 3: Plataformas ──────────────────────────────────────────────────────
# langfuse-server, n8n y evolution tienen healthcheck desactivado:
# sus imágenes no incluyen curl/wget y escuchan en la IP de red (no localhost).
# Se les da tiempo via sleep antes de arrancar sus dependientes.
phase "Fase 3 — Plataformas (langfuse-server, n8n, evolution)"

log "Arrancando langfuse-server, n8n y evolution…"
$DC_PROFILE up -d --remove-orphans --no-deps langfuse-server n8n evolution

log "Esperando 90s para que las plataformas inicialicen completamente…"
for i in $(seq 1 18); do
  sleep 5
  echo -ne "  ${YELLOW}…${NC} $((i*5))s / 90s\r"
done
echo ""
success "Plataformas arrancadas."

log "Arrancando langfuse-worker…"
$DC_PROFILE up -d --remove-orphans --no-deps langfuse-worker
log "Esperando 30s para que langfuse-worker inicialice…"
sleep 30
success "langfuse-worker arrancado."

if ! $SKIP_OBSERVABILITY; then
  log "Arrancando otel-collector…"
  $DC_PROFILE up -d --remove-orphans --no-deps otel-collector
  success "OTEL Collector arrancado."
fi

# ─── FASE 4: Gateway y UIs ────────────────────────────────────────────────────
phase "Fase 4 — Gateway y paneles web"

log "Arrancando webchat-gateway…"
$DC_PROFILE up -d --remove-orphans --no-deps webchat-gateway
wait_healthy webchat-gateway 180

if ! $SKIP_UI; then
  UI_SERVICES=(redis-insight rabbitmq-scout weaviate-gui)
  $SKIP_OBSERVABILITY || UI_SERVICES+=(opensearch-dashboards)

  log "Arrancando paneles web: ${UI_SERVICES[*]}"
  $DC_PROFILE up -d --remove-orphans --no-deps "${UI_SERVICES[@]}"
  success "Paneles web arrancados."
fi

# ─── FASE 5: Traefik (solo prod) ──────────────────────────────────────────────
if [[ "$PROFILE" == "prod" ]]; then
  phase "Fase 5 — Proxy inverso (Traefik)"
  $DC_PROFILE up -d --remove-orphans --no-deps traefik
  success "Traefik arrancado."
fi

# ─── Resumen final ────────────────────────────────────────────────────────────
phase "Stack listo"

echo -e "${BOLD}Estado de los contenedores:${NC}"
$DC_PROFILE ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

echo ""
success "Arranque completado en perfil '${PROFILE}'."
echo ""
echo -e "  Apagar todo:             ${CYAN}docker compose --profile $PROFILE down${NC}"
echo -e "  Ver logs en tiempo real: ${CYAN}docker compose --profile $PROFILE logs -f${NC}"
echo -e "  Estado detallado:        ${CYAN}docker compose --profile $PROFILE ps${NC}"