# ==============================================================================
# STAGE 1 — base
# Dependencias compartidas entre prod y dev.
# uv instala solo las deps de producción en el entorno del sistema.
# ==============================================================================
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /app

# Copiamos el binario de uv desde su imagen oficial
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Copiamos los manifiestos primero para aprovechar la caché de capas:
# si pyproject.toml y uv.lock no cambian, Docker reutiliza esta capa.
COPY pyproject.toml uv.lock* ./

# Instalamos solo dependencias de producción (sin dev extras)
RUN uv sync --frozen --no-dev

COPY app ./app

EXPOSE 8090

# ==============================================================================
# STAGE 2 — prod (default)
# CMD sin --reload ni --workers extra: uvicorn en modo producción.
# En producción se recomienda añadir workers según los cores disponibles:
#   --workers $(nproc) o un valor fijo como --workers 2
# ==============================================================================
FROM base AS prod

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8090", \
     "--workers", "2"]

# ==============================================================================
# STAGE 3 — dev
# Añade dependencias de desarrollo (linters, debuggers, etc.)
# y arranca con --reload apuntando solo a /app/app para evitar
# recargas innecesarias por cambios en pyproject.toml o uv.lock.
# El compose sobreescribe el CMD via `command:` de todas formas,
# pero lo dejamos explícito para poder hacer `docker run` directamente.
# ==============================================================================
FROM base AS dev

# Instalamos también las dependencias de dev (ej. pytest, ruff, etc.)
RUN uv sync --frozen

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8090", \
     "--reload", \
     "--reload-dir", "/app/app"]