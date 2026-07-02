#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
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

if [[ ! -d "${PROJECT_DIR}" ]]; then
  fail "project dir not found: ${PROJECT_DIR}"
fi
if [[ ! -f "${PROJECT_DIR}/${COMPOSE_FILE}" ]]; then
  fail "compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}"
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
COMPOSE=(docker compose -f "${COMPOSE_FILE}")

if ! "${COMPOSE[@]}" ps -q "${DB_SERVICE}" >/dev/null 2>&1; then
  fail "db service is not known: ${DB_SERVICE}"
fi
if ! "${COMPOSE[@]}" ps -q "${APP_SERVICE}" >/dev/null 2>&1; then
  fail "app service is not known: ${APP_SERVICE}"
fi

read_setting() {
  local setting="$1"
  "${COMPOSE[@]}" exec -T "${DB_SERVICE}" sh -lc \
    "psql -U \"\$POSTGRES_USER\" -d \"\${POSTGRES_DB:-air_conditioners}\" -Atqc \"SHOW ${setting}\""
}

archive_mode="$(read_setting archive_mode || true)"
archive_timeout="$(read_setting archive_timeout || true)"
archive_command="$(read_setting archive_command || true)"
in_recovery="$("${COMPOSE[@]}" exec -T "${DB_SERVICE}" sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -Atqc "SELECT pg_is_in_recovery()"' || true)"

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
  if [[ -z "${archive_timeout}" || "${archive_timeout}" == "0" ]]; then
    fail "archive_timeout is disabled"
  else
    ok "archive_timeout=${archive_timeout}"
  fi
  if [[ -z "${archive_command}" || "${archive_command}" == "(disabled)" ]]; then
    fail "archive_command is disabled"
  else
    ok "archive_command is configured"
  fi
else
  log info "archive_timeout=${archive_timeout:-<empty>} archive_command=${archive_command:-<empty>}"
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

archive_path="${ARCHIVE_DIR}"
if [[ "${archive_path}" != /* ]]; then
  archive_path="${PROJECT_DIR}/${archive_path}"
fi
if [[ -d "${archive_path}" ]]; then
  wal_count="$(find "${archive_path}" -maxdepth 1 -type f | wc -l | tr -d ' ')"
  wal_bytes="$(find "${archive_path}" -maxdepth 1 -type f -printf '%s\n' | awk '{sum += $1} END {print sum + 0}')"
  log info "local_archive_dir=${archive_path} files=${wal_count} bytes=${wal_bytes}"
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

remote_check=false
if [[ "${PITR_CHECK_REMOTE}" == "true" ]]; then
  remote_check=true
elif [[ "${PITR_CHECK_REMOTE}" == "auto" && "${PITR_REQUIRED}" == "true" ]]; then
  remote_check=true
fi

if [[ "${remote_check}" == "true" ]]; then
  if remote_output="$("${COMPOSE[@]}" run -T --rm "${APP_SERVICE}" python scripts/ha/check_postgres_pitr_remote.py \
    --max-wal-age-minutes "${PITR_MAX_WAL_AGE_MINUTES}" \
    --max-basebackup-age-hours "${PITR_MAX_BASEBACKUP_AGE_HOURS}" 2>&1)"; then
    print_prefixed remote "${remote_output}"
    ok "remote PITR object freshness passed"
  else
    print_prefixed remote "${remote_output}"
    fail "remote PITR object freshness failed"
  fi
else
  ok "remote PITR object check skipped"
fi

if (( failures > 0 )); then
  log summary "status=failed failures=${failures} warnings=${warnings}"
  exit 1
fi

log summary "status=passed failures=0 warnings=${warnings}"
