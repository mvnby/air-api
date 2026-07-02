#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
APP_SERVICE="${APP_SERVICE:-app}"
DB_SERVICE="${DB_SERVICE:-db}"
POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:15-alpine}"
DRILL_DIR="${DRILL_DIR:-/tmp/mvn-restore-drill}"
KEEP_DRILL_CONTAINER="${KEEP_DRILL_CONTAINER:-false}"
KEEP_DRILL_FILES="${KEEP_DRILL_FILES:-false}"

log() {
  printf '[restore-drill] %s\n' "$*"
}

cd "${PROJECT_DIR}"
if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "Compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}" >&2
  exit 1
fi

COMPOSE=(docker compose -f "${COMPOSE_FILE}")
mkdir -p "${DRILL_DIR}"
chmod 700 "${DRILL_DIR}"

container="mvn_restore_drill_$(date -u +%Y%m%d%H%M%S)"
backup_path=""
sql_path="${DRILL_DIR}/latest-db-backup.sql"

cleanup() {
  if [[ "${KEEP_DRILL_CONTAINER}" != "true" ]]; then
    docker rm -f "${container}" >/dev/null 2>&1 || true
  fi
  if [[ "${KEEP_DRILL_FILES}" != "true" ]]; then
    rm -f "${DRILL_DIR}"/latest-db-backup*
  fi
}
trap cleanup EXIT

db_container="$("${COMPOSE[@]}" ps -q "${DB_SERVICE}")"
if [[ -z "${db_container}" ]]; then
  echo "DB service is not running: ${DB_SERVICE}" >&2
  exit 1
fi

mapfile -t db_env < <("${COMPOSE[@]}" exec -T "${DB_SERVICE}" sh -lc 'printf "%s\n%s\n%s\n" "$POSTGRES_USER" "$POSTGRES_PASSWORD" "${POSTGRES_DB:-air_conditioners}"')
POSTGRES_USER="${db_env[0]:-}"
POSTGRES_PASSWORD="${db_env[1]:-}"
POSTGRES_DB="${db_env[2]:-air_conditioners}"

if [[ -z "${POSTGRES_USER}" || -z "${POSTGRES_PASSWORD}" || -z "${POSTGRES_DB}" ]]; then
  echo "Could not read POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB from ${DB_SERVICE} container." >&2
  exit 1
fi

network="$(docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "${db_container}" | head -n 1)"
if [[ -z "${network}" ]]; then
  echo "Could not detect Docker network for ${DB_SERVICE}" >&2
  exit 1
fi

log "Downloading latest DB backup from Google Drive via ${APP_SERVICE}..."
"${COMPOSE[@]}" run -T --rm -v "${DRILL_DIR}:/restore-drill" "${APP_SERVICE}" python - <<'PY'
from pathlib import Path
from services.backup_service import backup_service

items = backup_service.list_backups(limit=100)
latest = next((item for item in items if item.get("kind") == "db"), None)
if not latest:
    raise SystemExit("No DB backups found")

name = Path(str(latest.get("name") or "latest-db-backup.sql")).name
dest = Path("/restore-drill") / f"latest-db-backup{name[name.rfind('.'):] if '.' in name else '.sql'}"
if name.endswith(".sql.gz"):
    dest = Path("/restore-drill/latest-db-backup.sql.gz")
elif name.endswith(".sql"):
    dest = Path("/restore-drill/latest-db-backup.sql")

backup_service.download_backup_file(str(latest["id"]), str(dest))
print(f"backup_name={name}")
print(f"backup_created_at={latest.get('created_at')}")
print(f"backup_size_bytes={latest.get('size_bytes')}")
print(f"downloaded_path={dest}")
PY

if [[ -f "${DRILL_DIR}/latest-db-backup.sql.gz" ]]; then
  backup_path="${DRILL_DIR}/latest-db-backup.sql.gz"
  gzip -dc "${backup_path}" > "${sql_path}"
elif [[ -f "${DRILL_DIR}/latest-db-backup.sql" ]]; then
  backup_path="${DRILL_DIR}/latest-db-backup.sql"
else
  echo "Downloaded backup file was not found in ${DRILL_DIR}" >&2
  exit 1
fi

sed -i.bak '/^SET transaction_timeout = .*;$/d' "${sql_path}"
rm -f "${sql_path}.bak"

log "Starting disposable PostgreSQL container on network ${network}..."
docker run -d \
  --name "${container}" \
  --network "${network}" \
  -e POSTGRES_USER="${POSTGRES_USER}" \
  -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  -e POSTGRES_DB="${POSTGRES_DB}" \
  "${POSTGRES_IMAGE}" >/dev/null

for _ in $(seq 1 30); do
  if docker exec "${container}" pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! docker exec "${container}" pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
  docker logs "${container}" || true
  echo "Disposable PostgreSQL did not become ready." >&2
  exit 1
fi

log "Restoring backup into disposable PostgreSQL..."
docker cp "${sql_path}" "${container}:/tmp/restore.sql"
if ! docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${container}" \
  psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -f /tmp/restore.sql \
  >"${DRILL_DIR}/restore.log" 2>&1; then
  tail -n 120 "${DRILL_DIR}/restore.log" || true
  echo "Restore drill failed during psql restore." >&2
  exit 1
fi

tables_count="$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${container}" psql -Atqc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" \
  -U "${POSTGRES_USER}" -d "${POSTGRES_DB}")"

if [[ "${tables_count}" -lt 10 ]]; then
  echo "Restore drill produced too few public tables: ${tables_count}" >&2
  exit 1
fi

log "public_tables=${tables_count}"
docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${container}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" <<'SQL'
SELECT 'product_count=' || count(*) FROM product;
SELECT 'payment_count=' || count(*) FROM payment;
SELECT 'order_count=' || count(*) FROM "order";
SQL

log "restore drill passed; production and standby databases were not modified"
