#!/bin/bash
# ==============================================================================
# init-db.sh — Crea múltiples bases de datos en el arranque de Postgres
# Referenciado desde docker-compose.yml via:
#   ./init-db.sh:/docker-entrypoint-initdb.d/init-db.sh:ro
#
# Lee la variable POSTGRES_MULTIPLE_DATABASES (lista separada por comas)
# y crea cada base de datos si no existe.
# ==============================================================================
set -e

if [ -z "$POSTGRES_MULTIPLE_DATABASES" ]; then
  echo "INFO: POSTGRES_MULTIPLE_DATABASES no definida, saltando."
  exit 0
fi

echo "INFO: Creando bases de datos: $POSTGRES_MULTIPLE_DATABASES"

for DB in $(echo "$POSTGRES_MULTIPLE_DATABASES" | tr ',' ' '); do
  echo "  → Creando base de datos: $DB"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE "$DB"'
    WHERE NOT EXISTS (
      SELECT FROM pg_database WHERE datname = '$DB'
    )\gexec

    GRANT ALL PRIVILEGES ON DATABASE "$DB" TO "postgres";
EOSQL
done

echo "INFO: Bases de datos creadas correctamente."
