#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-}"
COMPOSE_FILE="${COMPOSE_FILE:-}"
APP_SERVICE="${APP_SERVICE:-app}"
DB_SERVICE="${DB_SERVICE:-db}"
ARCHIVE_DIR="${ARCHIVE_DIR:-postgres-wal-archive}"
PITR_REQUIRED="${PITR_REQUIRED:-${POSTGRES_PITR_REQUIRED:-false}}"
PITR_CHECK_REMOTE="${PITR_CHECK_REMOTE:-auto}"
PITR_MAX_LOCAL_WAL_FILES="${PITR_MAX_LOCAL_WAL_FILES:-24}"
PITR_MAX_LOCAL_WAL_BYTES="${PITR_MAX_LOCAL_WAL_BYTES:-536870912}"
PITR_MAX_ARCHIVER_FAILURES="${PITR_MAX_ARCHIVER_FAILURES:-0}"
PITR_MAX_WAL_AGE_MINUTES="${PITR_MAX_WAL_AGE_MINUTES:-180}"
PITR_MAX_BASEBACKUP_AGE_HOURS="${PITR_MAX_BASEBACKUP_AGE_HOURS:-30}"
RUNTIME_CHECK_HELPER="${RUNTIME_CHECK_HELPER:-/usr/local/sbin/mvn-postgres-pitr-runtime-check}"
TOOL_RUNNER="/usr/local/sbin/mvn-postgres-pitr-tool-runner"
PITR_OPERATION_ID="${PITR_OPERATION_ID:-}"
EXPECTED_ARCHIVE_COMMAND='/usr/local/bin/mvn-patroni-archive-wal "%p" "%f"'
EXPECTED_ARCHIVE_TIMEOUT="300"
WAL_SEGMENT_BYTES="16777216"
WAL_ARCHIVE_WAIT_SECONDS="330"

export DOCKER_CONTEXT="${DOCKER_CONTEXT:-default}"

failures=0
warnings=0

log() {
  local stage="$1"
  shift
  printf '[postgres-pitr][%s] %s\n' "${stage}" "$*"
}

ok() {
  log ok "$*"
}

warn() {
  warnings=$((warnings + 1))
  log warn "$*"
}

fail() {
  failures=$((failures + 1))
  log fail "$*"
}

normalize_bool() {
  case "$1" in
    true|TRUE|True|1|yes|YES|Yes|on|ON|On) printf 'true' ;;
    false|FALSE|False|0|no|NO|No|off|OFF|Off) printf 'false' ;;
    *) return 1 ;;
  esac
}

is_unsigned_int() {
  case "$1" in
    ''|*[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

is_unsigned_number() {
  [[ "$1" =~ ^[0-9]+([.][0-9]+)?$ ]]
}

print_prefixed() {
  local stage="$1"
  local content="$2"
  while IFS= read -r line; do
    if [[ -n "${line}" ]]; then
      log "${stage}" "${line}"
    fi
  done <<< "${content}"
}

is_uploadable_wal_name() {
  local filename="$1"
  [[ "${filename}" =~ ^[0-9A-F]{24}$ \
    || "${filename}" =~ ^[0-9A-F]{24}\.[0-9A-F]{8}\.backup$ \
    || "${filename}" =~ ^[0-9A-F]{8}\.history$ ]]
}

if ! PITR_REQUIRED="$(normalize_bool "${PITR_REQUIRED}")"; then
  fail "PITR_REQUIRED must be true or false"
fi
if [[ "${PITR_CHECK_REMOTE}" != "auto" ]]; then
  if ! PITR_CHECK_REMOTE="$(normalize_bool "${PITR_CHECK_REMOTE}")"; then
    fail "PITR_CHECK_REMOTE must be auto, true, or false"
  fi
fi
for value_name in \
  PITR_MAX_LOCAL_WAL_FILES \
  PITR_MAX_LOCAL_WAL_BYTES \
  PITR_MAX_ARCHIVER_FAILURES; do
  if ! is_unsigned_int "${!value_name}"; then
    fail "${value_name} must be an unsigned integer"
  fi
done
for value_name in PITR_MAX_WAL_AGE_MINUTES PITR_MAX_BASEBACKUP_AGE_HOURS; do
  if ! is_unsigned_number "${!value_name}"; then
    fail "${value_name} must be an unsigned number"
  fi
done

if [[ -z "${PROJECT_DIR}" ]]; then
  fail "PROJECT_DIR must be set"
elif [[ ! -d "${PROJECT_DIR}" ]]; then
  fail "project dir not found: ${PROJECT_DIR}"
fi
if [[ "${COMPOSE_FILE}" != "docker-compose.patroni.yml" ]]; then
  fail "COMPOSE_FILE must be docker-compose.patroni.yml"
elif [[ ! -f "${PROJECT_DIR}/${COMPOSE_FILE}" ]]; then
  fail "compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}"
fi
if [[ "${DOCKER_CONTEXT:-}" != "default" ]]; then
  fail "DOCKER_CONTEXT must be default"
fi
if ! command -v docker >/dev/null 2>&1; then
  fail "docker is not installed"
elif ! docker compose version >/dev/null 2>&1; then
  fail "docker compose is not available"
fi

if (( failures > 0 )); then
  log summary "status=failed failures=${failures} warnings=${warnings}"
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

if ! "${COMPOSE[@]}" ps -q "${DB_SERVICE}" >/dev/null 2>&1; then
  fail "db service is not known: ${DB_SERVICE}"
fi

read_scalar() {
  local sql="$1"
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" sh -lc \
    'exec psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -Atqc "$1"' \
    sh "${sql}"
}

read_setting() {
  local setting="$1"
  case "${setting}" in
    archive_mode|archive_timeout|archive_command) ;;
    *) return 64 ;;
  esac
  read_scalar "SELECT setting FROM pg_settings WHERE name = '${setting}'"
}

archive_mode="$(read_setting archive_mode || true)"
archive_timeout="$(read_setting archive_timeout || true)"
archive_command="$(read_setting archive_command || true)"
in_recovery="$(read_scalar 'SELECT pg_is_in_recovery()' || true)"
system_identifier="$(read_scalar 'SELECT system_identifier FROM pg_control_system()' || true)"

if [[ "${in_recovery}" == "t" ]]; then
  fail "this check must run on the current primary; db is in recovery"
elif [[ "${in_recovery}" == "f" ]]; then
  ok "db is writable primary"
else
  fail "could not read pg_is_in_recovery result: ${in_recovery:-<empty>}"
fi

if [[ "${archive_mode}" == "on" ]]; then
  ok "archive_mode=on"
elif [[ "${PITR_REQUIRED}" == "true" ]]; then
  fail "archive_mode is ${archive_mode:-<empty>}, expected on"
else
  ok "archive_mode=${archive_mode:-<empty>} and PITR_REQUIRED=false"
fi

if [[ "${PITR_REQUIRED}" == "true" ]]; then
  if [[ "${archive_timeout}" != "${EXPECTED_ARCHIVE_TIMEOUT}" ]]; then
    fail "archive_timeout=${archive_timeout:-<empty>}, expected ${EXPECTED_ARCHIVE_TIMEOUT}"
  else
    ok "archive_timeout=${EXPECTED_ARCHIVE_TIMEOUT}"
  fi
  if [[ "${archive_command}" != "${EXPECTED_ARCHIVE_COMMAND}" ]]; then
    fail "archive_command does not match the reviewed immutable WAL helper"
  else
    ok "archive_command matches the reviewed immutable WAL helper"
  fi
  if [[ ! "${PITR_OPERATION_ID}" =~ ^[0-9a-f]{32}$ ]]; then
    fail "PITR_OPERATION_ID must be a guarded operation ID"
  fi
else
  log info "archive_timeout=${archive_timeout:-<empty>} archive_command=${archive_command:-<empty>}"
fi

if [[ "${system_identifier}" =~ ^[1-9][0-9]{15,19}$ ]]; then
  ok "system identifier was read from pg_control_system()"
elif [[ "${PITR_REQUIRED}" == "true" || "${PITR_CHECK_REMOTE}" == "true" ]]; then
  fail "could not read a canonical PostgreSQL system identifier"
fi

archive_path="${ARCHIVE_DIR}"
if [[ "${archive_path}" != /* ]]; then
  archive_path="${PROJECT_DIR}/${archive_path}"
fi

remote_check=false
if [[ "${PITR_CHECK_REMOTE}" == "true" ]]; then
  remote_check=true
elif [[ "${PITR_CHECK_REMOTE}" == "auto" && "${PITR_REQUIRED}" == "true" ]]; then
  remote_check=true
fi
if [[ "${PITR_REQUIRED}" == "true" && "${remote_check}" != "true" ]]; then
  fail "strict PITR status cannot disable the remote proof"
fi

forced_wal=""
force_and_upload_exact_wal() {
  local switched_wal=""
  local wal_path=""
  local wal_metadata=""
  local deadline=0
  local upload_output=""
  local wal_ready="false"
  local force_sql=""

  if [[ ! -d "${archive_path}" || -L "${archive_path}" ]]; then
    log error "cannot force WAL: local archive directory is unavailable or unsafe"
    return 1
  fi
  if [[ ! -x "${TOOL_RUNNER}" ]]; then
    log error "cannot force WAL: isolated PITR tool runner is unavailable"
    return 1
  fi
  force_sql="WITH marker AS MATERIALIZED (SELECT pg_create_restore_point('mvn-pitr-status-${PITR_OPERATION_ID}') AS lsn) SELECT pg_walfile_name(pg_switch_wal()) FROM marker WHERE lsn IS NOT NULL"
  if ! switched_wal="$(read_scalar "${force_sql}")"; then
    log error "pg_switch_wal() failed"
    return 1
  fi
  if [[ ! "${switched_wal}" =~ ^[0-9A-F]{24}$ ]]; then
    log error "pg_switch_wal() returned a non-canonical segment"
    return 1
  fi
  forced_wal="${switched_wal}"
  wal_path="${archive_path}/${forced_wal}"
  deadline=$((SECONDS + WAL_ARCHIVE_WAIT_SECONDS))
  while (( SECONDS <= deadline )); do
    if [[ -e "${wal_path}" || -L "${wal_path}" ]]; then
      if [[ -L "${wal_path}" || ! -f "${wal_path}" ]]; then
        log error "forced WAL archive path is not a regular non-symlink file"
        return 1
      fi
      wal_metadata="$(stat -c '%F|%h|%s|%a' -- "${wal_path}" 2>/dev/null || true)"
      if [[ "${wal_metadata}" == "regular file|1|${WAL_SEGMENT_BYTES}|600" ]]; then
        wal_ready="true"
        break
      fi
      if [[ "${wal_metadata}" != "regular file|2|${WAL_SEGMENT_BYTES}|600" ]]; then
        log error "forced WAL archive file metadata is not canonical"
        return 1
      fi
    fi
    sleep 1
  done
  if [[ "${wal_ready}" != "true" ]]; then
    log error "timed out waiting for the exact forced WAL segment ${forced_wal}"
    return 1
  fi

  if ! upload_output="$(
    "${TOOL_RUNNER}" \
      --phase wal-upload \
      --data-dir "${archive_path}" \
      --delete-after-upload 2>&1
  )"; then
    print_prefixed upload "${upload_output}"
    log error "upload of the exact forced WAL segment failed"
    return 1
  fi
  print_prefixed upload "${upload_output}"
  if ! grep -Fq '"action": "uploaded_wal"' <<< "${upload_output}" \
    || ! grep -Fq "\"filename\": \"${forced_wal}\"" <<< "${upload_output}"; then
    log error "isolated uploader did not attest the exact forced WAL segment"
    return 1
  fi
  ok "forced and uploaded exact WAL segment ${forced_wal}"
}

if [[ "${PITR_REQUIRED}" == "true" && "${remote_check}" == "true" ]]; then
  if [[ "${archive_mode}" != "on" \
    || "${archive_timeout}" != "${EXPECTED_ARCHIVE_TIMEOUT}" \
    || "${archive_command}" != "${EXPECTED_ARCHIVE_COMMAND}" \
    || "${in_recovery}" != "f" \
    || ! "${system_identifier}" =~ ^[1-9][0-9]{15,19}$ \
    || ! "${PITR_OPERATION_ID}" =~ ^[0-9a-f]{32}$ ]]; then
    fail "strict WAL proof prerequisites are not satisfied"
  elif ! force_and_upload_exact_wal; then
    fail "strict forced WAL upload proof failed"
  fi
fi

archiver_output="$("${COMPOSE[@]}" exec -T "${DB_SERVICE}" sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -AtF "|"' <<'SQL' || true
SELECT
  archived_count,
  coalesce(last_archived_wal, '<none>'),
  coalesce(last_archived_time::text, '<none>'),
  failed_count,
  coalesce(last_failed_wal, '<none>'),
  coalesce(last_failed_time::text, '<none>')
FROM pg_stat_archiver;
SQL
)"
IFS='|' read -r archived_count last_archived_wal last_archived_time failed_count last_failed_wal last_failed_time <<< "${archiver_output}"
archived_count="${archived_count:-0}"
failed_count="${failed_count:-0}"

log info "archived_count=${archived_count} last_archived_wal=${last_archived_wal:-<none>} last_archived_time=${last_archived_time:-<none>}"
log info "failed_count=${failed_count} last_failed_wal=${last_failed_wal:-<none>} last_failed_time=${last_failed_time:-<none>}"

if [[ "${PITR_REQUIRED}" == "true" ]]; then
  if ! is_unsigned_int "${failed_count}"; then
    fail "pg_stat_archiver failed_count is not numeric: ${failed_count}"
  elif (( failed_count > PITR_MAX_ARCHIVER_FAILURES )); then
    fail "pg_stat_archiver failed_count=${failed_count} exceeds ${PITR_MAX_ARCHIVER_FAILURES}"
  else
    ok "pg_stat_archiver failed_count=${failed_count}"
  fi
fi

wal_count=0
wal_bytes=0
ignored_wal_count=0
if [[ -d "${archive_path}" ]]; then
  while IFS= read -r -d '' wal_path; do
    filename="${wal_path##*/}"
    if is_uploadable_wal_name "${filename}"; then
      wal_count=$((wal_count + 1))
      wal_bytes=$((wal_bytes + $(stat -c '%s' "${wal_path}")))
    else
      ignored_wal_count=$((ignored_wal_count + 1))
    fi
  done < <(find "${archive_path}" -maxdepth 1 -type f -print0)
  log info "local_archive_dir=${archive_path} files=${wal_count} bytes=${wal_bytes} ignored_files=${ignored_wal_count}"
  if [[ "${PITR_REQUIRED}" == "true" ]]; then
    if (( wal_count > PITR_MAX_LOCAL_WAL_FILES )); then
      fail "local WAL backlog files=${wal_count} exceeds ${PITR_MAX_LOCAL_WAL_FILES}"
    else
      ok "local WAL backlog files=${wal_count}"
    fi
    if (( wal_bytes > PITR_MAX_LOCAL_WAL_BYTES )); then
      fail "local WAL backlog bytes=${wal_bytes} exceeds ${PITR_MAX_LOCAL_WAL_BYTES}"
    else
      ok "local WAL backlog bytes=${wal_bytes}"
    fi
  elif (( wal_count > 0 )); then
    warn "PITR is not required but local WAL archive dir is not empty: files=${wal_count} bytes=${wal_bytes}"
  fi
elif [[ "${PITR_REQUIRED}" == "true" ]]; then
  fail "local WAL archive dir is missing: ${archive_path}"
else
  ok "local WAL archive dir is not present and PITR_REQUIRED=false"
fi

check_timer() {
  local timer="$1"
  if ! command -v systemctl >/dev/null 2>&1; then
    if [[ "${PITR_REQUIRED}" == "true" ]]; then
      fail "systemctl unavailable; cannot verify ${timer}"
    else
      warn "systemctl unavailable; skipped ${timer}"
    fi
    return
  fi

  if systemctl is-active --quiet "${timer}"; then
    ok "timer active: ${timer}"
  elif [[ "${PITR_REQUIRED}" == "true" ]]; then
    fail "timer is not active: ${timer}"
  else
    ok "timer inactive while PITR_REQUIRED=false: ${timer}"
  fi
}

check_timer mvn-postgres-wal-upload.timer
check_timer mvn-postgres-basebackup.timer

if [[ "${remote_check}" == "true" ]]; then
  if [[ ! "${system_identifier}" =~ ^[1-9][0-9]{15,19}$ ]]; then
    fail "remote PITR proof requires the live PostgreSQL system identifier"
  elif [[ "${PITR_REQUIRED}" == "true" && ! "${forced_wal}" =~ ^[0-9A-F]{24}$ ]]; then
    fail "strict remote PITR proof requires the exact forced WAL segment"
  else
    remote_args=(
      --phase remote-status
      --max-wal-age-minutes "${PITR_MAX_WAL_AGE_MINUTES}"
      --max-basebackup-age-hours "${PITR_MAX_BASEBACKUP_AGE_HOURS}"
      --local-pending-wal-count "${wal_count}"
      --expected-system-identifier "${system_identifier}"
    )
    if [[ "${PITR_REQUIRED}" == "true" ]]; then
      remote_args+=(--expected-wal "${forced_wal}")
    elif [[ "${last_archived_wal}" =~ ^[0-9A-F]{24}$ ]]; then
      remote_args+=(--expected-wal "${last_archived_wal}")
    fi
    if remote_output="$(
      "${TOOL_RUNNER}" "${remote_args[@]}" 2>&1
    )"; then
      print_prefixed remote "${remote_output}"
      if [[ "${PITR_REQUIRED}" == "true" ]] \
        && grep -q 'pitr_remote_wal status=idle' <<< "${remote_output}"; then
        fail "the exact forced WAL object is stale after its upload"
      elif grep -q 'pitr_remote_wal status=idle' <<< "${remote_output}"; then
        warn "remote WAL is older than the threshold, but no uploadable WAL is pending locally"
      else
        ok "remote PITR object freshness passed"
      fi
    else
      print_prefixed remote "${remote_output}"
      fail "remote PITR object freshness failed"
    fi
  fi
else
  ok "remote PITR object check skipped"
fi

if (( failures > 0 )); then
  log summary "status=failed failures=${failures} warnings=${warnings}"
  exit 1
fi

log summary "status=passed failures=0 warnings=${warnings}"
