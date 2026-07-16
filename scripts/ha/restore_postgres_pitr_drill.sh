#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-}"
COMPOSE_FILE="${COMPOSE_FILE:-}"
APP_SERVICE="${APP_SERVICE:-app}"
DB_SERVICE="${DB_SERVICE:-db}"
POSTGRES_IMAGE="postgres:15.18-alpine@sha256:3d0f7584ed7d04e27fa050d6683a74746608faf21f202be78460d679cc56461f"
POSTGRES_CONTAINER_UID="70"
POSTGRES_CONTAINER_GID="70"
MAX_TIMELINE_HISTORY_FILES="1024"
DRILL_DIR="/var/lib/mvn-postgres-pitr/restore-drills"
RESTORE_MOUNT_PATH="${RESTORE_MOUNT_PATH:-/pitr-restore}"
TARGET_TIME="${TARGET_TIME:-${PITR_RESTORE_TARGET_TIME:-}}"
BACKUP_ID="${BACKUP_ID:-${PITR_RESTORE_BACKUP_ID:-}}"
REQUIRE_WAL="${REQUIRE_WAL:-${PITR_RESTORE_REQUIRE_WAL:-true}}"
EXPECT_RECOVERY_PAUSED="${EXPECT_RECOVERY_PAUSED:-true}"
START_TIMEOUT_SECONDS="${START_TIMEOUT_SECONDS:-180}"
ARCHIVE_TIMEOUT_SECONDS="${ARCHIVE_TIMEOUT_SECONDS:-180}"
KEEP_DRILL_CONTAINER="${KEEP_DRILL_CONTAINER:-false}"
KEEP_DRILL_FILES="${KEEP_DRILL_FILES:-false}"
RUNTIME_CHECK_HELPER="${RUNTIME_CHECK_HELPER:-/usr/local/sbin/mvn-postgres-pitr-runtime-check}"
TOOL_RUNNER="/usr/local/sbin/mvn-postgres-pitr-tool-runner"
WAL_LINEAGE_HELPER="/usr/local/sbin/mvn-postgres-pitr-wal-lineage"
PITR_OPERATION_ID="${PITR_OPERATION_ID:-}"

umask 077
export DOCKER_CONTEXT="${DOCKER_CONTEXT:-default}"

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

sanitize_restored_config() {
  local name=""
  local path=""
  local links=""
  for name in postgresql.conf postgresql.auto.conf; do
    path="${target_dir}/data/${name}"
    links="$(stat -Lc '%h' "${path}" 2>/dev/null || true)"
    if [[ -L "${path}" || ! -f "${path}" || "${links}" != "1" ]]; then
      echo "Restored PostgreSQL configuration surface is unsafe: ${name}" >&2
      return 1
    fi
    printf '%s\n' '# Neutralized by the MVN isolated restore drill.' > "${path}"
    chown "${POSTGRES_CONTAINER_UID}:${POSTGRES_CONTAINER_GID}" "${path}"
    chmod 0600 "${path}"
  done
  path="${target_dir}/data/standby.signal"
  if [[ -e "${path}" || -L "${path}" ]]; then
    links="$(stat -Lc '%h' "${path}" 2>/dev/null || true)"
    if [[ -L "${path}" || ! -f "${path}" || "${links}" != "1" ]]; then
      echo "Restored PostgreSQL standby signal is unsafe" >&2
      return 1
    fi
    rm -- "${path}"
  fi
}

target_mode="restore_point"
target_epoch=""
if [[ -n "${TARGET_TIME}" ]]; then
  target_mode="time"
  [[ "${TARGET_TIME}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || {
    echo "TARGET_TIME must be canonical UTC (YYYY-MM-DDTHH:MM:SSZ)" >&2
    exit 1
  }
  target_epoch="$(date -u -d "${TARGET_TIME}" '+%s' 2>/dev/null || true)"
  target_roundtrip="$(date -u -d "${TARGET_TIME}" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || true)"
  if ! is_unsigned_int "${target_epoch}" || [[ "${target_roundtrip}" != "${TARGET_TIME}" ]] ||
    (( target_epoch >= $(date -u '+%s') )); then
    echo "TARGET_TIME must be a valid canonical UTC timestamp strictly in the past" >&2
    exit 1
  fi
fi

if ! REQUIRE_WAL="$(normalize_bool "${REQUIRE_WAL}")"; then
  echo "REQUIRE_WAL must be true or false" >&2
  exit 1
fi
if [[ "${REQUIRE_WAL}" != "true" ]]; then
  echo "Operational PITR drills require a complete archived WAL chain" >&2
  exit 1
fi
if ! EXPECT_RECOVERY_PAUSED="$(normalize_bool "${EXPECT_RECOVERY_PAUSED}")"; then
  echo "EXPECT_RECOVERY_PAUSED must be true or false" >&2
  exit 1
fi
if [[ "${EXPECT_RECOVERY_PAUSED}" != "true" ]]; then
  echo "Operational PITR drills must pause at the configured recovery target" >&2
  exit 1
fi
if ! KEEP_DRILL_CONTAINER="$(normalize_bool "${KEEP_DRILL_CONTAINER}")"; then
  echo "KEEP_DRILL_CONTAINER must be true or false" >&2
  exit 1
fi
if ! KEEP_DRILL_FILES="$(normalize_bool "${KEEP_DRILL_FILES}")"; then
  echo "KEEP_DRILL_FILES must be true or false" >&2
  exit 1
fi
if ! is_unsigned_int "${START_TIMEOUT_SECONDS}" ||
  (( START_TIMEOUT_SECONDS < 1 || START_TIMEOUT_SECONDS > 900 )); then
  echo "START_TIMEOUT_SECONDS must be between 1 and 900" >&2
  exit 1
fi
if ! is_unsigned_int "${ARCHIVE_TIMEOUT_SECONDS}" ||
  (( ARCHIVE_TIMEOUT_SECONDS < 1 || ARCHIVE_TIMEOUT_SECONDS > 900 )); then
  echo "ARCHIVE_TIMEOUT_SECONDS must be between 1 and 900" >&2
  exit 1
fi
if [[ ! "${RESTORE_MOUNT_PATH}" =~ ^/[A-Za-z0-9._/-]+$ || "${RESTORE_MOUNT_PATH}" == *".."* ]]; then
  echo "RESTORE_MOUNT_PATH is invalid" >&2
  exit 1
fi
if [[ -n "${BACKUP_ID}" && ! "${BACKUP_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; then
  echo "BACKUP_ID is invalid" >&2
  exit 1
fi

if [[ -z "${PROJECT_DIR}" ]]; then
  echo "PROJECT_DIR must be set" >&2
  exit 1
fi
if (( EUID != 0 )); then
  echo "PITR restore drill must run as root" >&2
  exit 1
fi
if [[ ! "${PITR_OPERATION_ID}" =~ ^[0-9a-f]{32}$ ]]; then
  echo "PITR_OPERATION_ID must be a guarded operation ID" >&2
  exit 1
fi
if [[ ! -d "${PROJECT_DIR}" ]]; then
  echo "Project dir not found: ${PROJECT_DIR}" >&2
  exit 1
fi
if [[ "${COMPOSE_FILE}" != "docker-compose.patroni.yml" ]]; then
  echo "COMPOSE_FILE must be docker-compose.patroni.yml" >&2
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
if [[ "${DOCKER_CONTEXT:-}" != "default" ]]; then
  echo "DOCKER_CONTEXT must be default" >&2
  exit 1
fi

cd "${PROJECT_DIR}"
BACKEND_IMAGE="$(
  "${RUNTIME_CHECK_HELPER}" \
    --project-dir "${PROJECT_DIR}" \
    --compose-file "${COMPOSE_FILE}"
)"
export BACKEND_IMAGE
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

db_env_output="$(
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" sh -lc \
    'printf "%s\n%s\n" "$POSTGRES_USER" "${POSTGRES_DB:-air_conditioners}"'
)" || {
  echo "Could not read PostgreSQL user/database identity from ${DB_SERVICE}" >&2
  exit 1
}
mapfile -t db_env <<< "${db_env_output}"
POSTGRES_USER="${db_env[0]:-}"
POSTGRES_DB="${db_env[1]:-}"
if [[ -z "${POSTGRES_USER}" || -z "${POSTGRES_DB}" ]]; then
  echo "Could not read PostgreSQL user/database identity from ${DB_SERVICE}" >&2
  exit 1
fi

[[ -x "${TOOL_RUNNER}" ]] || { echo "PITR tool runner is unavailable" >&2; exit 1; }
[[ -x "${WAL_LINEAGE_HELPER}" ]] || {
  echo "PITR WAL lineage helper is unavailable" >&2
  exit 1
}
live_state="$(
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" psql -v ON_ERROR_STOP=1 \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -AtF '|' \
    -c "SELECT s.system_identifier::text, a.last_archived_wal, extract(epoch FROM a.last_archived_time)::bigint, NOT pg_is_in_recovery(), pg_size_bytes(current_setting('wal_segment_size'))::bigint FROM pg_control_system() AS s CROSS JOIN pg_stat_archiver AS a"
)" || {
  echo "Could not read live PostgreSQL lineage and archive state" >&2
  exit 1
}
IFS='|' read -r live_system_identifier required_end_wal last_archived_epoch live_primary wal_segment_bytes unexpected_live <<< "${live_state}"
if [[ -n "${unexpected_live}" ]]; then
  echo "Live PostgreSQL lineage query returned an invalid shape" >&2
  exit 1
fi
if [[ ! "${live_system_identifier}" =~ ^[1-9][0-9]{15,19}$ ]]; then
  echo "Live PostgreSQL system identifier is invalid" >&2
  exit 1
fi
if [[ "${live_primary}" != "t" ]]; then
  echo "Refusing PITR drill on a non-primary DB service" >&2
  exit 1
fi
if [[ "${wal_segment_bytes}" != "16777216" ]]; then
  echo "Live PostgreSQL WAL segment size does not match the reviewed archive contract" >&2
  exit 1
fi
target_name=""
target_lsn=""
archive_dir="${PROJECT_DIR}/postgres-wal-archive"
[[ -d "${archive_dir}" && ! -L "${archive_dir}" ]] || {
  echo "Reviewed local WAL archive directory is unavailable" >&2
  exit 1
}
if [[ "${target_mode}" == "time" ]]; then
  if [[ ! "${required_end_wal}" =~ ^[0-9A-F]{24}$ ]] ||
    ! is_unsigned_int "${last_archived_epoch}" || (( last_archived_epoch < target_epoch )); then
    echo "Last archived WAL does not prove TARGET_TIME coverage" >&2
    exit 1
  fi
else
  target_name="mvn_pitr_${PITR_OPERATION_ID}"
  point_state="$(
    "${COMPOSE[@]}" exec -T "${DB_SERVICE}" psql -v ON_ERROR_STOP=1 \
      -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -AtF '|' \
      -c "WITH point AS MATERIALIZED (SELECT pg_create_restore_point('${target_name}') AS lsn), switched AS MATERIALIZED (SELECT pg_switch_wal() AS lsn FROM point) SELECT point.lsn::text, pg_walfile_name(point.lsn), pg_walfile_name(switched.lsn) FROM point CROSS JOIN switched"
  )" || { echo "Could not create the drill restore point and switch WAL" >&2; exit 1; }
  IFS='|' read -r target_lsn required_end_wal switched_wal unexpected_point <<< "${point_state}"
  if [[ -n "${unexpected_point}" || ! "${target_lsn}" =~ ^[0-9A-F]{1,8}/[0-9A-F]{1,8}$ ||
    ! "${required_end_wal}" =~ ^[0-9A-F]{24}$ || ! "${switched_wal}" =~ ^[0-9A-F]{24}$ ]]; then
    echo "PostgreSQL returned an invalid restore-point proof" >&2
    exit 1
  fi
  archive_ready=false
  for _ in $(seq 1 "${ARCHIVE_TIMEOUT_SECONDS}"); do
    if [[ -f "${archive_dir}/${required_end_wal}" && ! -L "${archive_dir}/${required_end_wal}" ]] &&
      [[ "$(stat -Lc '%s' "${archive_dir}/${required_end_wal}" 2>/dev/null || true)" == "${wal_segment_bytes}" ]]; then
      archive_ready=true
      break
    fi
    sleep 1
  done
  [[ "${archive_ready}" == "true" ]] || {
    echo "Restore-point WAL was not archived before timeout" >&2
    exit 1
  }

fi

# PostgreSQL only archives a timeline history file when that timeline is
# created.  A cluster adopted after earlier promotions can therefore have the
# original history chain in PGDATA but not in the new remote archive.  Reuse
# the image-pinned, create-only archive helper to stage every ancestor before
# the strict remote lineage check.  This is required for both target modes.
history_output="$(
  "${COMPOSE[@]}" exec -T --user \
    "${POSTGRES_CONTAINER_UID}:${POSTGRES_CONTAINER_GID}" \
    "${DB_SERVICE}" sh -ceu '
      maximum="$1"
      data_dir="${PGDATA:-/var/lib/postgresql/data}"
      count=0
      for source in "${data_dir}"/pg_wal/*.history; do
        [ -e "${source}" ] || continue
        count=$((count + 1))
        if [ "${count}" -gt "${maximum}" ]; then
          echo "Too many PostgreSQL timeline history files" >&2
          exit 1
        fi
        name="${source##*/}"
        /usr/local/bin/mvn-patroni-archive-wal \
          "${source}" "${name}"
        printf "%s\n" "${name}"
      done
    ' -- "${MAX_TIMELINE_HISTORY_FILES}"
)" || {
  echo "Could not stage the complete PostgreSQL timeline history chain" >&2
  exit 1
}
staged_history_count="$(printf '%s\n' "${history_output}" | sed '/^$/d' | wc -l | tr -d ' ')"
if ! is_unsigned_int "${staged_history_count}"; then
  echo "PostgreSQL timeline history staging returned an invalid result" >&2
  exit 1
fi
validated_history_output="$(
  "${WAL_LINEAGE_HELPER}" validate-local-history \
    --archive-dir "${archive_dir}" \
    --required-end-wal "${required_end_wal}"
)" || {
  echo "Local PostgreSQL timeline history failed strict lineage validation" >&2
  exit 1
}
validated_history_count="$(printf '%s\n' "${validated_history_output}" | sed '/^$/d' | wc -l | tr -d ' ')"
if ! is_unsigned_int "${validated_history_count}"; then
  echo "PostgreSQL timeline history validation returned an invalid result" >&2
  exit 1
fi
log "staged_timeline_history_files=${staged_history_count} validated_lineage_history_files=${validated_history_count} required_end_timeline=${required_end_wal:0:8}"
"${TOOL_RUNNER}" --phase wal-upload --data-dir "${archive_dir}"
log "target_mode=${target_mode} target_time=${TARGET_TIME:-<none>} target_name=${target_name:-<none>} target_lsn=${target_lsn:-<none>} expected_system_identifier=${live_system_identifier} required_end_wal=${required_end_wal}"

run_dir="${DRILL_DIR}/${PITR_OPERATION_ID}"
target_dir="${run_dir}/restore"
container="mvn-pitr-restore-drill-${PITR_OPERATION_ID}"

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

state_contract="$(stat -Lc '%u:%g:%a:%h' "${DRILL_DIR}" 2>/dev/null || true)"
IFS=: read -r state_uid state_gid state_mode state_links <<< "${state_contract}"
if [[ -L "${DRILL_DIR}" || ! -d "${DRILL_DIR}" ||
  "${state_uid}" != "0" || "${state_gid}" != "0" ||
  "${state_mode}" != "700" || ! "${state_links}" =~ ^[0-9]+$ ]]; then
  echo "PITR restore-drill state directory is unsafe" >&2
  exit 1
fi
if (( state_links < 2 )); then
  echo "PITR restore-drill state directory is unsafe" >&2
  exit 1
fi
mkdir -- "${run_dir}"
mkdir -- "${target_dir}"

prepare_args=(
  --phase restore-prepare
  --data-dir "${target_dir}"
  --expected-system-identifier "${live_system_identifier}"
  --required-end-wal "${required_end_wal}"
)
if [[ "${target_mode}" == "time" ]]; then
  prepare_args+=(--target-time "${TARGET_TIME}")
else
  prepare_args+=(--target-name "${target_name}" --target-lsn "${target_lsn}")
fi
if [[ -n "${BACKUP_ID}" ]]; then
  prepare_args+=(--backup-id "${BACKUP_ID}")
fi

log "preparing isolated PITR restore under ${target_dir}"
"${TOOL_RUNNER}" "${prepare_args[@]}" | tee "${run_dir}/prepare.log"

if [[ ! -d "${target_dir}/data" ]]; then
  echo "Prepared PITR restore is missing data dir: ${target_dir}/data" >&2
  exit 1
fi
if [[ ! -d "${target_dir}/wal" ]]; then
  echo "Prepared PITR restore is missing WAL dir: ${target_dir}/wal" >&2
  exit 1
fi
if [[ ! -f "${target_dir}/downloads/backup_manifest" ||
  ! -f "${target_dir}/data/PG_VERSION" ||
  "$(<"${target_dir}/data/PG_VERSION")" != "15" ]]; then
  echo "Prepared PITR restore is not a compatible PostgreSQL 15 basebackup" >&2
  exit 1
fi
if [[ -L "${target_dir}/control" || ! -d "${target_dir}/control" ||
  -L "${target_dir}/control/postgresql.conf" ||
  ! -f "${target_dir}/control/postgresql.conf" ]]; then
  echo "Prepared PITR restore is missing its known-safe control config" >&2
  exit 1
fi

log "verifying extracted basebackup against PostgreSQL backup_manifest"
if ! docker run --pull never --rm \
  --name "${container}-verify" \
  --label "com.mvn.pitr.operation=${PITR_OPERATION_ID}" \
  --label "com.mvn.pitr.phase=restore-verify" \
  --network none \
  --read-only \
  --user 0:0 \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 64 \
  --memory 512m \
  --cpus 1.0 \
  --entrypoint pg_verifybackup \
  --mount "type=bind,source=${target_dir}/data,target=/var/lib/postgresql/data,readonly" \
  --mount "type=bind,source=${target_dir}/downloads/backup_manifest,target=/pitr-control/backup_manifest,readonly" \
  "${POSTGRES_IMAGE}" \
  --exit-on-error \
  --no-parse-wal \
  --manifest-path=/pitr-control/backup_manifest \
  /var/lib/postgresql/data >"${run_dir}/pg_verifybackup.log" 2>&1; then
  tail -n 160 "${run_dir}/pg_verifybackup.log" || true
  echo "pg_verifybackup rejected the extracted PITR basebackup" >&2
  exit 1
fi
sanitize_restored_config

wal_count="$(find "${target_dir}/wal" -maxdepth 1 -type f | wc -l | tr -d ' ')"
if ! is_unsigned_int "${wal_count}" || (( wal_count < 1 )); then
  echo "PITR restore drill expected a verified archived WAL chain" >&2
  exit 1
fi
unexpected_wal_entry="$(
  find "${target_dir}/wal" -mindepth 1 -maxdepth 1 ! -type f -print -quit
)"
if [[ -n "${unexpected_wal_entry}" ]]; then
  echo "Prepared PITR WAL directory contains an unexpected entry" >&2
  exit 1
fi
chown "${POSTGRES_CONTAINER_UID}:${POSTGRES_CONTAINER_GID}" "${target_dir}/wal"
find "${target_dir}/wal" -mindepth 1 -maxdepth 1 -type f \
  -exec chown "${POSTGRES_CONTAINER_UID}:${POSTGRES_CONTAINER_GID}" {} +
chmod 0500 "${target_dir}/wal"
find "${target_dir}/wal" -mindepth 1 -maxdepth 1 -type f -exec chmod 0400 {} +

drill_hba="${target_dir}/control/pg_hba.conf"
printf '%s\n' \
  'local all all trust' \
  'host all all all reject' > "${drill_hba}"
printf '%s\n' '# intentionally empty' > "${target_dir}/control/pg_ident.conf"
chown -R "${POSTGRES_CONTAINER_UID}:${POSTGRES_CONTAINER_GID}" "${target_dir}/control"
chmod 0500 "${target_dir}/control"
find "${target_dir}/control" -mindepth 1 -maxdepth 1 -type f -exec chmod 0400 {} +
log "downloaded_wal_files=${wal_count}"

log "starting network-isolated disposable PostgreSQL container"
docker run --pull never -d \
  --name "${container}" \
  --label "com.mvn.pitr.operation=${PITR_OPERATION_ID}" \
  --label "com.mvn.pitr.phase=restore-drill" \
  --network none \
  --read-only \
  --cap-drop ALL \
  --cap-add CHOWN \
  --cap-add DAC_OVERRIDE \
  --cap-add SETGID \
  --cap-add SETUID \
  --security-opt no-new-privileges:true \
  --pids-limit 256 \
  --memory 4g \
  --memory-swap 4g \
  --cpus 2.0 \
  --shm-size 256m \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  --tmpfs /var/run/postgresql:rw,nosuid,nodev,size=16m \
  --mount "type=bind,source=${target_dir}/data,target=/var/lib/postgresql/data" \
  --volume "${target_dir}/wal:${RESTORE_MOUNT_PATH}/wal:ro" \
  --volume "${target_dir}/control:/pitr-control:ro" \
  "${POSTGRES_IMAGE}" \
  postgres \
  -c "config_file=/pitr-control/postgresql.conf" \
  -c "data_directory=/var/lib/postgresql/data" \
  -c "listen_addresses=" \
  -c "unix_socket_directories=/var/run/postgresql" \
  -c "hba_file=/pitr-control/pg_hba.conf" \
  -c "ident_file=/pitr-control/pg_ident.conf" \
  -c "shared_preload_libraries=" \
  -c "session_preload_libraries=" \
  -c "local_preload_libraries=" \
  -c "dynamic_library_path=" \
  -c "jit=off" \
  -c "archive_command=" \
  -c "archive_library=" \
  -c "archive_cleanup_command=" \
  -c "recovery_end_command=" \
  -c "primary_conninfo=" \
  -c "primary_slot_name=" \
  -c "ssl_passphrase_command=" \
  -c "ssl=off" >/dev/null

if [[ "${target_mode}" == "time" ]]; then
  configured_target_sql="extract(epoch FROM current_setting('recovery_target_time')::timestamptz)::bigint::text"
  target_progress_sql="true"
else
  configured_target_sql="current_setting('recovery_target_name')"
  target_progress_sql="pg_last_wal_replay_lsn() >= '${target_lsn}'::pg_lsn"
fi

# PostgreSQL starts accepting read-only connections as soon as it reaches a
# consistent recovery state.  That is deliberately earlier than the requested
# restore point, so pg_isready alone cannot prove that the drill is complete.
# Poll the recovery state until replay has reached and paused at the exact
# target, or fail closed when the bounded startup window expires.
state=""
target_reached=false
for _ in $(seq 1 "${START_TIMEOUT_SECONDS}"); do
  if state="$(
    docker exec --user postgres "${container}" \
      psql -v ON_ERROR_STOP=1 -AtF '|' \
      -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
      -c "SELECT pg_is_in_recovery(), CASE WHEN pg_is_in_recovery() THEN pg_is_wal_replay_paused() ELSE false END, coalesce(pg_last_wal_replay_lsn()::text, ''), coalesce(extract(epoch FROM pg_last_xact_replay_timestamp())::bigint::text, ''), s.system_identifier::text, current_setting('config_file'), current_setting('hba_file'), current_setting('ident_file'), current_setting('data_directory'), ${configured_target_sql}, ${target_progress_sql} FROM pg_control_system() AS s" \
      2>/dev/null
  )"; then
    IFS='|' read -r current_in_recovery current_replay_paused _ _ _ _ _ _ _ _ current_target_progress current_unexpected <<< "${state}"
    if [[ -z "${current_unexpected}" && "${current_in_recovery}" == "t" &&
      "${current_replay_paused}" == "t" && "${current_target_progress}" == "t" ]]; then
      target_reached=true
      break
    fi
  fi
  sleep 1
done

if [[ "${target_reached}" != "true" ]]; then
  docker logs --tail=160 "${container}" || true
  echo "Disposable PostgreSQL did not reach and pause at the configured recovery target" >&2
  exit 1
fi
IFS='|' read -r restored_in_recovery restored_replay_paused restored_replay_lsn replay_timestamp_epoch restored_system_identifier restored_config_file restored_hba_file restored_ident_file restored_data_directory configured_target target_progress unexpected_restored <<< "${state}"

log "restored_in_recovery=${restored_in_recovery}"
log "restored_replay_paused=${restored_replay_paused}"
log "restored_replay_lsn=${restored_replay_lsn}"
log "replay_timestamp_epoch=${replay_timestamp_epoch}"
log "restored_system_identifier=${restored_system_identifier}"
log "restored_config_file=${restored_config_file} restored_data_directory=${restored_data_directory}"
log "configured_target=${configured_target} target_progress=${target_progress}"

if [[ -n "${unexpected_restored}" || "${restored_in_recovery}" != "t" ||
  "${restored_replay_paused}" != "t" ]]; then
  docker logs --tail=160 "${container}" || true
  echo "Recovery did not pause at the configured target" >&2
  exit 1
fi
if [[ ! "${restored_replay_lsn}" =~ ^[0-9A-F]{1,8}/[0-9A-F]{1,8}$ ||
  "${restored_replay_lsn}" == "0/0" ]]; then
  echo "Restored PostgreSQL replay LSN is invalid" >&2
  exit 1
fi
if [[ "${restored_system_identifier}" != "${live_system_identifier}" ]]; then
  echo "Restored PostgreSQL system identifier does not match the live cluster" >&2
  exit 1
fi
if [[ "${restored_config_file}" != "/pitr-control/postgresql.conf" ||
  "${restored_hba_file}" != "/pitr-control/pg_hba.conf" ||
  "${restored_ident_file}" != "/pitr-control/pg_ident.conf" ||
  "${restored_data_directory}" != "/var/lib/postgresql/data" ]]; then
  echo "Restored PostgreSQL is not using the reviewed isolated configuration" >&2
  exit 1
fi
if [[ "${target_progress}" != "t" ]]; then
  echo "Restored PostgreSQL replay LSN did not reach the configured target" >&2
  exit 1
fi
if [[ "${target_mode}" == "time" ]]; then
  if ! is_unsigned_int "${replay_timestamp_epoch}" || (( replay_timestamp_epoch > target_epoch )) ||
    ! is_unsigned_int "${configured_target}" || (( configured_target != target_epoch )); then
    echo "Restored PostgreSQL did not stop at TARGET_TIME" >&2
    exit 1
  fi
elif [[ "${configured_target}" != "${target_name}" ||
  ( -n "${replay_timestamp_epoch}" && ! "${replay_timestamp_epoch}" =~ ^[0-9]+$ ) ]]; then
  echo "Restored PostgreSQL did not stop at the exact named restore point" >&2
  exit 1
fi
log "target_reached=true target_mode=${target_mode} replay_lsn=${restored_replay_lsn}"

tables_count="$(
  docker exec --user postgres "${container}" \
    psql -v ON_ERROR_STOP=1 -Atqc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'" \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
)"
if ! is_unsigned_int "${tables_count}" || (( tables_count < 10 )); then
  echo "PITR restore drill produced too few public tables: ${tables_count}" >&2
  exit 1
fi
log "public_tables=${tables_count}"

business_counts="$(
  docker exec --user postgres "${container}" \
    psql -v ON_ERROR_STOP=1 -AtF '|' \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c 'SELECT (SELECT count(*) FROM product), (SELECT count(*) FROM payment), (SELECT count(*) FROM "order")'
)"
IFS='|' read -r product_count payment_count order_count unexpected_counts <<< "${business_counts}"
if [[ -n "${unexpected_counts}" ]]; then
  echo "PITR restore drill returned invalid business counts: ${business_counts}" >&2
  exit 1
fi
for count in "${product_count}" "${payment_count}" "${order_count}"; do
  if ! is_unsigned_int "${count}"; then
    echo "PITR restore drill returned invalid business counts: ${business_counts}" >&2
    exit 1
  fi
done
log "product_count=${product_count} payment_count=${payment_count} order_count=${order_count}"
if [[ "${product_count}" -lt 1 || "${order_count}" -lt 1 ]]; then
  echo "PITR restore drill is missing required product/order data: ${business_counts}" >&2
  exit 1
fi

log "PITR restore drill passed; production and standby databases were not modified"
