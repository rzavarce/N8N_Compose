# 🚀 AI Automation & Observability Stack

Ecosistema completo para el despliegue de automatizaciones de IA, gestión de mensajería y observabilidad avanzada. Diseñado para funcionar en desarrollo local y escalar a producción con un único cambio de perfil.

---

## 📋 Tabla de Contenidos

1. [Arquitectura de Servicios](#1-arquitectura-de-servicios)
2. [Perfiles de Docker](#2-perfiles-de-docker)
3. [Requisitos Previos](#3-requisitos-previos)
4. [Instalación y Construcción](#4-instalación-y-construcción-evolution-api)
5. [Despliegue General](#5-despliegue-general)
6. [Configuración Inicial de Base de Datos](#6-configuración-inicial-de-base-de-datos)
7. [Acceso a los Servicios](#7-acceso-a-los-servicios)
8. [Troubleshooting](#8-troubleshooting)
9. [Notas de Mantenimiento](#9-notas-de-mantenimiento)

---

## 1. Arquitectura de Servicios

```
┌─────────────────────────────────────────────────────────┐
│                    proxy_network                         │
│   ┌──────────┐                                          │
│   │ Traefik  │ ← SSL + Routing (solo prod)              │
│   └────┬─────┘                                          │
└────────│────────────────────────────────────────────────┘
         │
┌────────▼────────────────────────────────────────────────┐
│                   backend_network                        │
│                                                          │
│  Orquestación         Mensajería         Persistencia    │
│  ┌─────────┐          ┌──────────┐       ┌──────────┐   │
│  │   n8n   │          │Evolution │       │Postgres  │   │
│  └────┬────┘          │   API    │       │  :5432   │   │
│       │               └────┬─────┘       └──────────┘   │
│       │                    │             ┌──────────┐   │
│  Observabilidad        Broker/Cache      │  Redis   │   │
│  ┌──────────┐          ┌──────────┐      │  :6379   │   │
│  │ Langfuse │          │RabbitMQ  │      └──────────┘   │
│  └────┬─────┘          │  :5672   │                     │
│       │                └──────────┘      Vectorial       │
│  ┌────┴──────┐                          ┌──────────┐    │
│  │ClickHouse │         Logs             │ Weaviate │    │
│  └───────────┘    ┌────────────┐        │  :8081   │    │
│                   │ OpenSearch │        └──────────┘    │
│  Telemetría       │  :9200     │                        │
│  ┌───────────┐    └────────────┘                        │
│  │OtelCollect│                                          │
│  └───────────┘                                          │
└─────────────────────────────────────────────────────────┘
```

| Servicio              | Imagen                                  | Rol                                           |
|-----------------------|-----------------------------------------|-----------------------------------------------|
| **n8n**               | `n8nio/n8n:2.18.7`                      | Motor de flujos de automatización             |
| **Evolution API**     | `rzavarce/evolution-api:2.3.7`          | Gateway WhatsApp / mensajería                 |
| **Langfuse**          | `langfuse/langfuse:3`                   | Observabilidad y trazabilidad LLM             |
| **PostgreSQL**        | `postgres:17-alpine`                    | Base de datos principal (n8n, Langfuse, Evo)  |
| **Redis**             | `redis:7-alpine`                        | Caché de Evolution API y n8n                  |
| **RabbitMQ**          | `rabbitmq:3.12-management-alpine`       | Broker de mensajes                            |
| **Weaviate**          | `semitechnologies/weaviate:1.24.1`      | Base de datos vectorial para RAG              |
| **ClickHouse**        | `clickhouse/clickhouse-server:24.3`     | Base de datos OLAP para Langfuse              |
| **OpenSearch**        | `opensearchproject/opensearch:2.12.0`   | Almacenamiento de logs                        |
| **OpenSearch Dash.**  | `opensearchproject/opensearch-dashboards:2.12.0` | UI de visualización de logs        |
| **OTel Collector**    | `otel/opentelemetry-collector-contrib:0.96.0` | Recolección de trazas OpenTelemetry     |
| **Traefik**           | `traefik:v2.10`                         | Proxy inverso, SSL automático (prod)          |

---

## 2. Perfiles de Docker

El `docker-compose.yml` usa perfiles para controlar qué servicios se levantan:

| Perfil | Servicios activos | Uso recomendado |
|--------|-------------------|-----------------|
| `dev`  | Postgres, Redis, RabbitMQ, Weaviate, Evolution, n8n | Desarrollo local |
| `prod` | Todo lo anterior + ClickHouse, Langfuse, OpenSearch, Dashboards, OTel Collector, Traefik | Servidor de producción |

> **Nota sobre redes:** En `dev`, la `backend_network` es abierta para permitir el acceso desde herramientas externas como DBeaver. En `prod`, puedes cambiarla a `internal: true` ya que Traefik gestiona el tráfico externo.

---

## 3. Requisitos Previos

- Docker >= 24.x
- Docker Compose >= 2.x (plugin integrado en Docker Desktop)
- Git

Para verificar:
```bash
docker --version
docker compose version
```

---

## 4. Instalación y Construcción (Evolution API)

> ⚠️ La imagen de Evolution API **debe construirse localmente** antes de lanzar el stack.

```bash
# 1. Clonar el repositorio oficial
git clone https://github.com/EvolutionAPI/evolution-api.git
cd evolution-api

# 2. Cambiar a la versión estable usada en el compose
git checkout 2.3.5   # o la versión que corresponda

# 3. Construir la imagen con el tag definido en el compose
docker build -t rzavarce/evolution-api:2.3.7 .

# 4. Volver a la raíz del proyecto
cd ..

# 5. Crear colleccion, se debe realizar por workflows
TODO: automarizar de alguna manera
cd ..


curl -X POST http://localhost:8081/v1/schema   -H "Content-Type: application/json"   -d '{
    "class": "Documents",
    "vectorizer": "none",
    "properties": [
      {"name": "text", "dataType": ["text"]},
      {"name": "source", "dataType": ["text"]}
    ]
  }'

```

---

## 5. Despliegue General

### Paso 1 — Configurar variables de entorno

```bash
cp env.example .env
```

Editar `.env` y revisar especialmente:

| Variable | Descripción |
|----------|-------------|
| `POSTGRES_PASSWORD` | Cambiar en producción |
| `RABBIT_PASS` | Cambiar en producción |
| `EVOLUTION_API_KEY` | Clave de autenticación de la API |
| `N8N_ENCRYPTION_KEY` | Debe ser exactamente 32 caracteres |
| `NEXTAUTH_SECRET` | Secreto para sesiones de Langfuse |
| `SSL_EMAIL` | Email para certificados Let's Encrypt (prod) |
| `DOMAIN_*` | Dominios para Traefik (descomentar en prod) |

> ⚠️ **Importante:** No uses comentarios inline en los valores del `.env` (ej: `VAR=valor # comentario`). Algunos parsers incluyen el comentario como parte del valor. Usa líneas separadas con `#`.

### Paso 2 — Levantar el stack

```bash
# Desarrollo
docker compose --profile dev up -d

# Producción
docker compose --profile prod up -d
```

### Paso 3 — Verificar estado

```bash
# Ver estado de todos los contenedores
docker compose ps

# Seguir logs en tiempo real
docker compose logs -f

# Logs de un servicio específico
docker compose logs -f n8n
docker compose logs -f evolution
```

---

## 6. Configuración Inicial de Base de Datos

El script `init-db.sh` crea automáticamente las bases de datos definidas en `POSTGRES_MULTIPLE_DATABASES` al primer arranque de Postgres.

Si necesitas crearlas manualmente:

```bash
docker exec -it ai_postgres psql -U admin -c "CREATE DATABASE workflowsdb;"
docker exec -it ai_postgres psql -U admin -c "CREATE DATABASE langfusedb;"
docker exec -it ai_postgres psql -U admin -c "CREATE DATABASE evolutiondb;"
```

Para verificar que existen:

```bash
docker exec -it ai_postgres psql -U admin -c "\l"
```

### Conexión desde DBeaver (desarrollo local)

| Campo    | Valor       |
|----------|-------------|
| Host     | `localhost` |
| Puerto   | `5432`      |
| Usuario  | `admin`     |
| Password | `admin123`  |

---

## 7. Acceso a los Servicios

### Desarrollo local (perfil `dev`)

| Servicio          | URL                              |
|-------------------|----------------------------------|
| n8n               | http://localhost:5678            |
| Evolution API     | http://localhost:8082            |
| Weaviate          | http://localhost:8081            |
| RabbitMQ UI       | http://localhost:15672           |

### Producción (perfil `prod`, vía Traefik HTTPS)

| Servicio            | URL                                        |
|---------------------|--------------------------------------------|
| n8n                 | https://workflows.zavarcecloud.com      |
| Evolution API       | https://wa.zavarcecloud.com         |
| Langfuse            | https://obs.zavarcecloud.com             |
| OpenSearch Dash.    | https://logs.zavarcecloud.com            |

---

## 8. Troubleshooting

### Evolution API falla con error de autenticación en Prisma

**Síntoma:** `P1000: Authentication failed... credentials for 'user' are not valid`

**Causa:** La imagen tiene un `.env` interno que puede sobreescribir las variables de Docker. Asegúrate de que en el `docker-compose.yml` uses `DATABASE_CONNECTION_URI` (no `DATABASE_URL`):

```yaml
- DATABASE_CONNECTION_URI=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:5432/${EVOLUTION_DB}?schema=public
- DATABASE_CONNECTION_CLIENT_NAME=evolution_api
```

### No puedo conectarme a Postgres desde DBeaver

**Causa más común:** `backend_network` configurada como `internal: true` bloquea el acceso desde el host aunque el puerto esté publicado.

**Solución:** En el `docker-compose.yml`, el perfil `dev` debe tener:

```yaml
networks:
  backend_network: {}   # Sin "internal: true" en dev
```

### n8n no arranca o muestra errores de protocolo

**Causa:** Comentario inline en el `.env`: `N8N_PROTOCOL=http #https en prod`

**Solución:** El valor queda como `http #https en prod`. Separar el comentario:

```env
# Cambiar a https en prod
N8N_PROTOCOL=http
```

### Postgres no levanta / datos corruptos

```bash
# Ver logs del contenedor
docker logs ai_postgres

# Si necesitas resetear el volumen (⚠️ elimina todos los datos)
docker compose down
rm -rf ./volumes/postgres
docker compose --profile dev up -d
```

### Reiniciar un servicio específico

```bash
docker compose up evolution --force-recreate -d
```

---

## 9. Notas de Mantenimiento

**Persistencia de datos:** Todos los volúmenes se almacenan en `./volumes/`. Hacer backup de este directorio es suficiente para preservar el estado del stack.

```
./volumes/
├── postgres/       # Datos de n8n, Langfuse y Evolution
├── weaviate/       # Índices vectoriales
├── clickhouse/     # Datos OLAP de Langfuse (prod)
└── opensearch/     # Logs del sistema (prod)
```

**Actualizar una imagen:**

```bash
# Editar la versión en docker-compose.yml, luego:
docker compose pull <servicio>
docker compose up <servicio> --force-recreate -d
```

**Parar el stack sin eliminar datos:**

```bash
docker compose --profile dev down
# Los volúmenes en ./volumes/ se conservan
```

**Parar y eliminar todo (incluidos volúmenes de Docker, no los de ./volumes/):**

```bash
docker compose --profile dev down -v
```

ssh -R zavarcecloud:80:localhost:5678 serveo.net


**N8N Workflow Template:**

https://n8n.io/workflows/2753-rag-chatbot-for-company-documents-using-google-drive-and-gemini/

---


{
  "requestId": "...",
  "channel": "webchat | n8n_chat | telegram | facebook | whatsapp | webhook",
  "sessionId": "...",
  "userId": "...",
  "message": "...",
  "modelName": "chatgpt",
  "replyMode": "websocket | push | n8n_response_node",
  "callbackUrl": "...",
  "socketSessionId": "...",
  "metadata": {}
}


¡Listo para automatizar! 🤖🔥