#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
APP_SERVICE="${APP_SERVICE:-app}"
DB_SERVICE="${DB_SERVICE:-db}"
POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:15.18-alpine@sha256:3d0f7584ed7d04e27fa050d6683a74746608faf21f202be78460d679cc56461f}"
DRILL_DIR="${DRILL_DIR:-/tmp/mvn-postgres-pitr-restore-drill}"
RESTORE_MOUNT_PATH="${RESTORE_MOUNT_PATH:-/pitr-restore}"
TARGET_TIME="${TARGET_TIME:-${PITR_RESTORE_TARGET_TIME:-}}"
BACKUP_ID="${BACKUP_ID:-${PITR_RESTORE_BACKUP_ID:-}}"
REQUIRE_WAL="${REQUIRE_WAL:-${PITR_RESTORE_REQUIRE_WAL:-true}}"
EXPECT_RECOVERY_PAUSED="${EXPECT_RECOVERY_PAUSED:-auto}"
START_TIMEOUT_SECONDS="${START_TIMEOUT_SECONDS:-180}"
KEEP_DRILL_CONTAINER="${KEEP_DRILL_CONTAINER:-false}"
KEEP_DRILL_FILES="${KEEP_DRILL_FILES:-false}"

log() {
  printf '[pitr-restore-drill] %s\n' "$*"
}

normalize_bool() {
  case "${1:-}" in
    true|TRUE|True|1|yes|YES|Yes|on|ON|On) printf 'true' ;;
    false|FALSE|False|0|no|NO|No|off|OFF|Off) printf 'false' ;;
    *) return 1 ;;
  esac
}

is_unsigned_int() {
  case "${1:-}" in
    ''|*[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

if ! REQUIRE_WAL="$(normalize_bool "${REQUIRE_WAL}")"; then
  echo "REQUIRE_WAL must be true or false" >&2
  exit 1
fi

if [[ "${EXPECT_RECOVERY_PAUSED}" == "auto" ]]; then
  if [[ -n "${TARGET_TIME}" ]]; then
    EXPECT_RECOVERY_PAUSED="true"
  else
    EXPECT_RECOVERY_PAUSED="false"
  fi
elif ! EXPECT_RECOVERY_PAUSED="$(normalize_bool "${EXPECT_RECOVERY_PAUSED}")"; then
  echo "EXPECT_RECOVERY_PAUSED must be auto, true, or false" >&2
  exit 1
fi

if ! is_unsigned_int "${START_TIMEOUT_SECONDS}"; then
  echo "START_TIMEOUT_SECONDS must be an unsigned integer" >&2
  exit 1
fi

if [[ ! -d "${PROJECT_DIR}" ]]; then
  echo "Project dir not found: ${PROJECT_DIR}" >&2
  exit 1
fi
if [[ ! -f "${PROJECT_DIR}/${COMPOSE_FILE}" ]]; then
  echo "Compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed" >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is not available" >&2
  exit 1
fi

cd "${PROJECT_DIR}"
COMPOSE=(docker compose -f "${COMPOSE_FILE}")

db_container="$("${COMPOSE[@]}" ps -q "${DB_SERVICE}")"
if [[ -z "${db_container}" ]]; then
  echo "DB service is not running: ${DB_SERVICE}" >&2
  exit 1
fi

if ! "${COMPOSE[@]}" config --services | grep -Fxq "${APP_SERVICE}"; then
  echo "App service is not defined in compose: ${APP_SERVICE}" >&2
  exit 1
fi

in_recovery="$("${COMPOSE[@]}" exec -T "${DB_SERVICE}" sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -Atqc "SELECT pg_is_in_recovery()"' || true)"
if [[ "${in_recovery}" != "f" ]]; then
  echo "Refusing PITR drill on a non-primary DB service; pg_is_in_recovery=${in_recovery:-<empty>}" >&2
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

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
run_dir="${DRILL_DIR}/${run_id}"
target_dir="${run_dir}/restore"
container="mvn_pitr_restore_drill_${run_id//[^A-Za-z0-9_]/_}"

cleanup() {
  if [[ "${KEEP_DRILL_CONTAINER}" != "true" ]]; then
    docker rm -f "${container}" >/dev/null 2>&1 || true
  fi
  if [[ "${KEEP_DRILL_FILES}" != "true" ]]; then
    rm -rf "${run_dir}"
  else
    log "kept drill files: ${run_dir}"
  fi
}
trap cleanup EXIT

mkdir -p "${target_dir}"
chmod 700 "${run_dir}" "${target_dir}"

prepare_args=(
  python
  scripts/ha/restore_postgres_pitr_from_s3.py
  prepare
  --target-dir "${RESTORE_MOUNT_PATH}"
  --wal-mode local
  --restore-mount-path "${RESTORE_MOUNT_PATH}"
)
if [[ -n "${BACKUP_ID}" ]]; then
  prepare_args+=(--backup-id "${BACKUP_ID}")
fi
if [[ -n "${TARGET_TIME}" ]]; then
  prepare_args+=(--target-time "${TARGET_TIME}")
fi

log "preparing isolated PITR restore under ${target_dir}"
"${COMPOSE[@]}" run -T --rm \
  -v "${target_dir}:${RESTORE_MOUNT_PATH}" \
  "${APP_SERVICE}" \
  "${prepare_args[@]}" | tee "${run_dir}/prepare.log"

if [[ ! -d "${target_dir}/data" ]]; then
  echo "Prepared PITR restore is missing data dir: ${target_dir}/data" >&2
  exit 1
fi
if [[ ! -d "${target_dir}/wal" ]]; then
  echo "Prepared PITR restore is missing WAL dir: ${target_dir}/wal" >&2
  exit 1
fi

wal_count="$(find "${target_dir}/wal" -maxdepth 1 -type f | wc -l | tr -d ' ')"
log "downloaded_wal_files=${wal_count}"
if [[ "${REQUIRE_WAL}" == "true" && "${wal_count}" -lt 1 ]]; then
  echo "PITR restore drill expected at least one archived WAL file." >&2
  exit 1
fi

log "starting disposable PostgreSQL container on network ${network}"
docker run -d \
  --name "${container}" \
  --network "${network}" \
  -e POSTGRES_USER="${POSTGRES_USER}" \
  -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  -e POSTGRES_DB="${POSTGRES_DB}" \
  -v "${target_dir}/data:/var/lib/postgresql/data" \
  -v "${target_dir}/wal:${RESTORE_MOUNT_PATH}/wal:ro" \
  "${POSTGRES_IMAGE}" \
  postgres >/dev/null

ready=false
for _ in $(seq 1 "${START_TIMEOUT_SECONDS}"); do
  if docker exec "${container}" pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done

if [[ "${ready}" != "true" ]]; then
  docker logs --tail=160 "${container}" || true
  echo "Disposable PostgreSQL did not become ready." >&2
  exit 1
fi

state="$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${container}" psql -AtF '|' \
  -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -c "SELECT pg_is_in_recovery(), CASE WHEN pg_is_in_recovery() THEN pg_is_wal_replay_paused() ELSE false END, CASE WHEN pg_is_in_recovery() THEN coalesce(pg_last_wal_replay_lsn()::text, '<none>') ELSE '<not-in-recovery>' END;")"
IFS='|' read -r restored_in_recovery restored_replay_paused restored_replay_lsn <<< "${state}"

log "restored_in_recovery=${restored_in_recovery}"
log "restored_replay_paused=${restored_replay_paused}"
log "restored_replay_lsn=${restored_replay_lsn}"

if [[ "${EXPECT_RECOVERY_PAUSED}" == "true" ]]; then
  if [[ "${restored_in_recovery}" != "t" || "${restored_replay_paused}" != "t" ]]; then
    docker logs --tail=160 "${container}" || true
    echo "Expected recovery to pause at target time, got in_recovery=${restored_in_recovery} paused=${restored_replay_paused}" >&2
    exit 1
  fi
fi

tables_count="$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${container}" psql -Atqc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" \
  -U "${POSTGRES_USER}" -d "${POSTGRES_DB}")"

if [[ "${tables_count}" -lt 10 ]]; then
  echo "PITR restore drill produced too few public tables: ${tables_count}" >&2
  exit 1
fi

log "public_tables=${tables_count}"
docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${container}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" <<'SQL'
SELECT 'product_count=' || count(*) FROM product;
SELECT 'payment_count=' || count(*) FROM payment;
SELECT 'order_count=' || count(*) FROM "order";
SQL

log "PITR restore drill passed; production and standby databases were not modified"
