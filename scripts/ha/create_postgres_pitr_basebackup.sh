#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
APP_SERVICE="${APP_SERVICE:-app}"
DB_SERVICE="${DB_SERVICE:-db}"
POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:15.18-alpine@sha256:3d0f7584ed7d04e27fa050d6683a74746608faf21f202be78460d679cc56461f}"
BACKUP_ROOT="${BACKUP_ROOT:-/tmp/mvn-postgres-pitr-basebackups}"
KEEP_LOCAL_BACKUP="${KEEP_LOCAL_BACKUP:-false}"
DRY_RUN_UPLOAD="${DRY_RUN_UPLOAD:-false}"

log() {
  printf '[pitr-basebackup] %s\n' "$*"
}

cd "${PROJECT_DIR}"
if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "Compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}" >&2
  exit 1
fi

COMPOSE=(docker compose -f "${COMPOSE_FILE}")
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

if ! "${COMPOSE[@]}" exec -T "${DB_SERVICE}" sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -Atqc "SELECT NOT pg_is_in_recovery()"' | grep -qx t; then
  echo "Refusing basebackup: ${DB_SERVICE} is not the writable primary." >&2
  exit 1
fi

backup_id="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT}/${backup_id}"
mkdir -p "${backup_dir}"
chmod 700 "${BACKUP_ROOT}" "${backup_dir}"

cleanup() {
  if [[ "${KEEP_LOCAL_BACKUP}" != "true" ]]; then
    rm -rf "${backup_dir}"
  fi
}
trap cleanup EXIT

# Join the DB container network namespace so Postgres sees this as localhost.
# The default pg_hba.conf allows local replication without opening replication
# to the whole Docker bridge network.
log "Creating physical pg_basebackup ${backup_id} through ${DB_SERVICE} localhost network namespace..."
docker run --rm \
  --network "container:${db_container}" \
  -e PGPASSWORD="${POSTGRES_PASSWORD}" \
  -e PGHOST="127.0.0.1" \
  -e PGUSER="${POSTGRES_USER}" \
  -e PGLABEL="mvn-pitr-${backup_id}" \
  -v "${backup_dir}:/backup" \
  "${POSTGRES_IMAGE}" \
  sh -lc 'pg_basebackup -h "$PGHOST" -U "$PGUSER" -D /backup -Ft -z -X stream -l "$PGLABEL" -P'

cat >"${backup_dir}/metadata.json" <<JSON
{
  "backup_id": "${backup_id}",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "project_dir": "${PROJECT_DIR}",
  "compose_file": "${COMPOSE_FILE}",
  "db_service": "${DB_SERVICE}",
  "postgres_db": "${POSTGRES_DB}"
}
JSON

log "Uploading physical basebackup ${backup_id} through ${APP_SERVICE}..."
upload_flags=()
if [[ "${DRY_RUN_UPLOAD}" == "true" ]]; then
  upload_flags+=(--dry-run)
fi

"${COMPOSE[@]}" run -T --rm \
  -v "${backup_dir}:/pitr-basebackup:ro" \
  "${APP_SERVICE}" \
  python scripts/ha/upload_postgres_pitr_to_s3.py basebackup \
    --source-dir /pitr-basebackup \
    --backup-id "${backup_id}" \
    "${upload_flags[@]}"

log "basebackup ${backup_id} completed"
