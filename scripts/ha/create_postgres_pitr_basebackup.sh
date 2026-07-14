#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-}"
COMPOSE_FILE="${COMPOSE_FILE:-}"
DB_SERVICE="${DB_SERVICE:-db}"
POSTGRES_IMAGE="postgres:15.18-alpine@sha256:3d0f7584ed7d04e27fa050d6683a74746608faf21f202be78460d679cc56461f"
BACKUP_ROOT="/var/lib/mvn-postgres-pitr/basebackups"
KEEP_LOCAL_BACKUP="${KEEP_LOCAL_BACKUP:-false}"
DRY_RUN_UPLOAD="${DRY_RUN_UPLOAD:-false}"
RUNTIME_CHECK_HELPER="${RUNTIME_CHECK_HELPER:-/usr/local/sbin/mvn-postgres-pitr-runtime-check}"
PITR_RUNTIME_POLICY="${PITR_RUNTIME_POLICY:-operational}"
TOOL_RUNNER="/usr/local/sbin/mvn-postgres-pitr-tool-runner"
PITR_OPERATION_ID="${PITR_OPERATION_ID:-}"

umask 077
export DOCKER_CONTEXT="${DOCKER_CONTEXT:-default}"

log() {
  printf '[pitr-basebackup] %s\n' "$*"
}

[[ -n "${PROJECT_DIR}" ]] || { echo "PROJECT_DIR must be set" >&2; exit 1; }
[[ "${PITR_OPERATION_ID}" =~ ^[0-9a-f]{32}$ ]] || {
  echo "PITR_OPERATION_ID must be a guarded operation ID" >&2
  exit 1
}
[[ "${COMPOSE_FILE}" == "docker-compose.patroni.yml" ]] || {
  echo "COMPOSE_FILE must be docker-compose.patroni.yml" >&2
  exit 1
}
[[ "${DOCKER_CONTEXT:-}" == "default" ]] || {
  echo "DOCKER_CONTEXT must be default" >&2
  exit 1
}
case "${PITR_RUNTIME_POLICY}" in
  configured|operational) ;;
  *) echo "PITR_RUNTIME_POLICY must be configured or operational" >&2; exit 1 ;;
esac
cd "${PROJECT_DIR}"
if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "Compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}" >&2
  exit 1
fi

BACKEND_IMAGE="$(
  "${RUNTIME_CHECK_HELPER}" \
    --project-dir "${PROJECT_DIR}" \
    --compose-file "${COMPOSE_FILE}" \
    --pitr-env-policy "${PITR_RUNTIME_POLICY}"
)"
export BACKEND_IMAGE

COMPOSE=(docker compose -f "${COMPOSE_FILE}")
db_container="$("${COMPOSE[@]}" ps -q "${DB_SERVICE}")"
if [[ -z "${db_container}" ]]; then
  echo "DB service is not running: ${DB_SERVICE}" >&2
  exit 1
fi

# Variables expand inside the DB container.
# shellcheck disable=SC2016
mapfile -t db_env < <("${COMPOSE[@]}" exec -T "${DB_SERVICE}" sh -lc 'printf "%s\n%s\n%s\n%s\n%s\n" "$PATRONI_REPLICATION_USERNAME" "$PATRONI_REPLICATION_PASSWORD" "$PATRONI_POSTGRESQL_CONNECT_ADDRESS" "${POSTGRES_DB:-air_conditioners}" "$PATRONI_NAME"')
REPLICATION_USER="${db_env[0]:-}"
REPLICATION_PASSWORD="${db_env[1]:-}"
POSTGRES_CONNECT_ADDRESS="${db_env[2]:-}"
POSTGRES_DB="${db_env[3]:-air_conditioners}"
SOURCE_NODE="${db_env[4]:-}"

if [[ -z "${REPLICATION_USER}" || -z "${REPLICATION_PASSWORD}" || -z "${POSTGRES_CONNECT_ADDRESS}" || -z "${POSTGRES_DB}" ]]; then
  echo "Could not read exact Patroni replication credentials/address from ${DB_SERVICE}." >&2
  exit 1
fi
case "${SOURCE_NODE}" in
  mvn-api|zakup) ;;
  *) echo "Patroni source node identity is invalid." >&2; exit 1 ;;
esac
if [[ ! "${POSTGRES_CONNECT_ADDRESS}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{1,5}$ ]]; then
  echo "Patroni PostgreSQL connect address is invalid." >&2
  exit 1
fi
PGHOST="${POSTGRES_CONNECT_ADDRESS%:*}"
PGPORT="${POSTGRES_CONNECT_ADDRESS##*:}"

# Variables expand inside the DB container.
# shellcheck disable=SC2016
if ! "${COMPOSE[@]}" exec -T "${DB_SERVICE}" sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -Atqc "SELECT NOT pg_is_in_recovery()"' | grep -qx t; then
  echo "Refusing basebackup: ${DB_SERVICE} is not the writable primary." >&2
  exit 1
fi

read_primary_identity() {
  # Variables expand inside the DB container.
  # shellcheck disable=SC2016
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" sh -lc \
    'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -AtF "|" -c "SELECT s.system_identifier::text, c.timeline_id::text, pg_current_wal_lsn()::text, NOT pg_is_in_recovery() FROM pg_control_system() AS s CROSS JOIN pg_control_checkpoint() AS c"'
}

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
identity_before="$(read_primary_identity)"
IFS='|' read -r system_identifier timeline start_lsn writable_before <<< "${identity_before}"
[[ "${system_identifier}" =~ ^[1-9][0-9]{15,19}$ ]] || {
  echo "PostgreSQL system identifier before basebackup is invalid." >&2
  exit 1
}
[[ "${timeline}" =~ ^[1-9][0-9]{0,9}$ ]] || {
  echo "PostgreSQL timeline before basebackup is invalid." >&2
  exit 1
}
[[ "${start_lsn}" =~ ^[0-9A-F]{1,8}/[0-9A-F]{1,8}$ && "${writable_before}" == "t" ]] || {
  echo "PostgreSQL primary lineage before basebackup is invalid." >&2
  exit 1
}

# A timestamp alone can collide across a fast retry or two physical hosts near
# a promotion.  Bind the immutable remote object namespace to both the proved
# Patroni member and the guarded operation instead.
backup_id="$(date -u +%Y%m%dT%H%M%SZ)-${SOURCE_NODE}-${PITR_OPERATION_ID}"
backup_dir="${BACKUP_ROOT}/${PITR_OPERATION_ID}"
state_contract="$(stat -Lc '%u:%g:%a:%h' "${BACKUP_ROOT}" 2>/dev/null || true)"
IFS=: read -r state_uid state_gid state_mode state_links <<< "${state_contract}"
if [[ -L "${BACKUP_ROOT}" || ! -d "${BACKUP_ROOT}" || "${state_uid}" != 0 || "${state_gid}" != 0 || "${state_mode}" != 700 ]]; then
  echo "PITR basebackup state directory is unsafe" >&2
  exit 1
fi
if [[ ! "${state_links}" =~ ^[0-9]+$ ]] || (( state_links < 2 )); then
  echo "PITR basebackup state directory is unsafe" >&2
  exit 1
fi
mkdir -- "${backup_dir}"

cleanup() {
  if [[ "${KEEP_LOCAL_BACKUP}" != "true" ]]; then
    rm -rf "${backup_dir}"
  fi
}
trap cleanup EXIT

# Join the DB network namespace and use Patroni's dedicated replication role
# against its reviewed 10.77/24 replication pg_hba rule.
log "Creating physical pg_basebackup ${backup_id} through ${DB_SERVICE} network namespace..."
PGPASSWORD="${REPLICATION_PASSWORD}" docker run --pull never --rm \
  --name "mvn-pitr-pg-basebackup-${PITR_OPERATION_ID}" \
  --label "com.mvn.pitr.operation=${PITR_OPERATION_ID}" \
  --label "com.mvn.pitr.phase=basebackup" \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 128 \
  --memory 768m \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,mode=0700 \
  --network "container:${db_container}" \
  -e PGPASSWORD \
  -e PGHOST="${PGHOST}" \
  -e PGPORT="${PGPORT}" \
  -e PGUSER="${REPLICATION_USER}" \
  -e PGLABEL="mvn-pitr-${backup_id}" \
  -v "${backup_dir}:/backup" \
  "${POSTGRES_IMAGE}" \
  sh -lc 'pg_basebackup -h "$PGHOST" -U "$PGUSER" -D /backup -Ft -z -X stream -l "$PGLABEL" -P'

identity_after="$(read_primary_identity)"
IFS='|' read -r system_identifier_after timeline_after end_lsn writable_after <<< "${identity_after}"
[[ "${system_identifier_after}" == "${system_identifier}" && "${timeline_after}" == "${timeline}" ]] || {
  echo "PostgreSQL lineage changed during basebackup." >&2
  exit 1
}
[[ "${end_lsn}" =~ ^[0-9A-F]{1,8}/[0-9A-F]{1,8}$ && "${writable_after}" == "t" ]] || {
  echo "PostgreSQL primary lineage after basebackup is invalid." >&2
  exit 1
}
completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat >"${backup_dir}/metadata.json" <<JSON
{
  "schema_version": 1,
  "backup_id": "${backup_id}",
  "system_identifier": "${system_identifier}",
  "timeline": ${timeline},
  "start_lsn": "${start_lsn}",
  "end_lsn": "${end_lsn}",
  "started_at": "${started_at}",
  "completed_at": "${completed_at}",
  "source_node": "${SOURCE_NODE}"
}
JSON

log "Uploading physical basebackup ${backup_id} through the isolated PITR runner..."
upload_flags=()
if [[ "${DRY_RUN_UPLOAD}" == "true" ]]; then
  upload_flags+=(--dry-run)
fi

[[ -x "${TOOL_RUNNER}" ]] || { echo "PITR tool runner is unavailable" >&2; exit 1; }
"${TOOL_RUNNER}" \
  --phase basebackup-upload \
  --data-dir "${backup_dir}" \
  --backup-id "${backup_id}" \
  --system-identifier "${system_identifier}" \
  --timeline "${timeline}" \
  --start-lsn "${start_lsn}" \
  --end-lsn "${end_lsn}" \
  --started-at "${started_at}" \
  --completed-at "${completed_at}" \
  --source-node "${SOURCE_NODE}" \
  "${upload_flags[@]}"

log "basebackup ${backup_id} completed"
