#!/usr/bin/env bash
set -euo pipefail

PRIMARY_SSH="${PRIMARY_SSH:-mvn-api}"
STANDBY_SSH="${STANDBY_SSH:-zakup}"
PRIMARY_PROJECT_DIR="${PRIMARY_PROJECT_DIR:-/opt/air-api}"
PRIMARY_COMPOSE_FILE="${PRIMARY_COMPOSE_FILE:-docker-compose.prod.yml}"
STANDBY_PROJECT_DIR="${STANDBY_PROJECT_DIR:-/opt/mvn-reserve}"
STANDBY_COMPOSE_FILE="${STANDBY_COMPOSE_FILE:-docker-compose.reserve.yml}"
PRIMARY_DB_SERVICE="${PRIMARY_DB_SERVICE:-db}"
STANDBY_DB_SERVICE="${STANDBY_DB_SERVICE:-db}"
EXPECTED_SLOT="${EXPECTED_SLOT:-zakup_standby}"
EXPECTED_STANDBY_APPLICATION="${EXPECTED_STANDBY_APPLICATION:-walreceiver}"
EXPECTED_PRIMARY_WG_IP="${EXPECTED_PRIMARY_WG_IP:-10.77.0.2}"
EXPECTED_STANDBY_WG_IP="${EXPECTED_STANDBY_WG_IP:-10.77.0.1}"
MAX_REPLAY_LAG_BYTES="${MAX_REPLAY_LAG_BYTES:-16777216}"
SSH_OPTS="${SSH_OPTS:-}"

failures=0
warnings=0

log() {
  local level="$1"
  shift
  printf '[postgres-replication][%s] %s\n' "${level}" "$*"
}

fail() {
  failures=$((failures + 1))
  log fail "$*"
}

warn() {
  warnings=$((warnings + 1))
  log warn "$*"
}

ok() {
  log ok "$*"
}

info() {
  log info "$*"
}

is_unsigned_int() {
  case "$1" in
    ''|*[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

quote_remote() {
  printf '%q' "$1"
}

run_remote_sql() {
  local ssh_target="$1"
  local project_dir="$2"
  local compose_file="$3"
  local db_service="$4"
  local sql="$5"
  local remote_cmd

  remote_cmd="cd $(quote_remote "${project_dir}") && docker compose -f $(quote_remote "${compose_file}") exec -T $(quote_remote "${db_service}") sh -lc 'psql -U \"\$POSTGRES_USER\" -d \"\${POSTGRES_DB:-air_conditioners}\" -AtF \"|\"'"
  # shellcheck disable=SC2086
  ssh ${SSH_OPTS} "${ssh_target}" "${remote_cmd}" <<< "${sql}"
}

validate_inputs() {
  if [[ ! "${EXPECTED_SLOT}" =~ ^[A-Za-z0-9_]+$ ]]; then
    fail "EXPECTED_SLOT must contain only letters, numbers, and underscore"
  fi
  if [[ ! "${EXPECTED_STANDBY_APPLICATION}" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    fail "EXPECTED_STANDBY_APPLICATION must contain only letters, numbers, underscore, dot, or dash"
  fi
  if [[ -n "${EXPECTED_STANDBY_WG_IP}" && ! "${EXPECTED_STANDBY_WG_IP}" =~ ^[0-9A-Fa-f:.]+$ ]]; then
    fail "EXPECTED_STANDBY_WG_IP must be an IP address"
  fi
  if [[ -n "${EXPECTED_PRIMARY_WG_IP}" && ! "${EXPECTED_PRIMARY_WG_IP}" =~ ^[0-9A-Fa-f:.]+$ ]]; then
    fail "EXPECTED_PRIMARY_WG_IP must be an IP address"
  fi
  if ! is_unsigned_int "${MAX_REPLAY_LAG_BYTES}"; then
    fail "MAX_REPLAY_LAG_BYTES must be an unsigned integer"
  fi
  if [[ -z "${PRIMARY_SSH}" || -z "${STANDBY_SSH}" ]]; then
    fail "PRIMARY_SSH and STANDBY_SSH must be set"
  fi
}

validate_inputs
if (( failures > 0 )); then
  log summary "status=failed failures=${failures} warnings=${warnings}"
  exit 1
fi

primary_recovery="$(
  run_remote_sql "${PRIMARY_SSH}" "${PRIMARY_PROJECT_DIR}" "${PRIMARY_COMPOSE_FILE}" "${PRIMARY_DB_SERVICE}" \
    "select pg_is_in_recovery();"
)"
if [[ "${primary_recovery}" == "f" ]]; then
  ok "primary database is writable primary"
else
  fail "primary database should not be in recovery; got ${primary_recovery:-<empty>}"
fi

primary_replication_sql="
select
  coalesce(application_name, ''),
  coalesce(host(client_addr), ''),
  coalesce(state, ''),
  coalesce(sync_state, ''),
  coalesce(sent_lsn::text, ''),
  coalesce(write_lsn::text, ''),
  coalesce(flush_lsn::text, ''),
  coalesce(replay_lsn::text, ''),
  coalesce(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::bigint::text, '')
from pg_stat_replication
where ('${EXPECTED_STANDBY_WG_IP}' = '' or host(client_addr) = '${EXPECTED_STANDBY_WG_IP}')
order by application_name
limit 1;
"
primary_replication="$(
  run_remote_sql "${PRIMARY_SSH}" "${PRIMARY_PROJECT_DIR}" "${PRIMARY_COMPOSE_FILE}" "${PRIMARY_DB_SERVICE}" \
    "${primary_replication_sql}"
)"
if [[ -z "${primary_replication}" ]]; then
  fail "primary has no pg_stat_replication row for standby ${EXPECTED_STANDBY_WG_IP:-<any>}"
else
  IFS='|' read -r application_name client_addr state sync_state sent_lsn write_lsn flush_lsn replay_lsn replay_lag_bytes <<< "${primary_replication}"
  info "primary replication application=${application_name:-<empty>} client_addr=${client_addr:-<empty>} state=${state:-<empty>} sync_state=${sync_state:-<empty>} sent_lsn=${sent_lsn:-<empty>} replay_lsn=${replay_lsn:-<empty>} replay_lag_bytes=${replay_lag_bytes:-<empty>}"
  if [[ "${state}" == "streaming" ]]; then
    ok "primary sees standby streaming"
  else
    fail "primary replication state is ${state:-<empty>}, expected streaming"
  fi
  if [[ -n "${EXPECTED_STANDBY_APPLICATION}" && "${application_name}" != "${EXPECTED_STANDBY_APPLICATION}" ]]; then
    fail "primary replication application_name=${application_name:-<empty>}, expected ${EXPECTED_STANDBY_APPLICATION}"
  fi
  if [[ -n "${EXPECTED_STANDBY_WG_IP}" && "${client_addr}" != "${EXPECTED_STANDBY_WG_IP}" ]]; then
    fail "primary sees standby client_addr=${client_addr:-<empty>}, expected ${EXPECTED_STANDBY_WG_IP}"
  fi
  if ! is_unsigned_int "${replay_lag_bytes}"; then
    fail "primary replay lag is not numeric: ${replay_lag_bytes:-<empty>}"
  elif (( replay_lag_bytes <= MAX_REPLAY_LAG_BYTES )); then
    ok "primary replay lag ${replay_lag_bytes} bytes <= ${MAX_REPLAY_LAG_BYTES}"
  else
    fail "primary replay lag ${replay_lag_bytes} bytes exceeds ${MAX_REPLAY_LAG_BYTES}"
  fi
fi

primary_slot_sql="
select
  slot_name,
  slot_type,
  active::text,
  coalesce(restart_lsn::text, ''),
  coalesce(wal_status, ''),
  coalesce(safe_wal_size::text, '')
from pg_replication_slots
where slot_name = '${EXPECTED_SLOT}';
"
primary_slot="$(
  run_remote_sql "${PRIMARY_SSH}" "${PRIMARY_PROJECT_DIR}" "${PRIMARY_COMPOSE_FILE}" "${PRIMARY_DB_SERVICE}" \
    "${primary_slot_sql}"
)"
if [[ -z "${primary_slot}" ]]; then
  fail "primary replication slot is missing: ${EXPECTED_SLOT}"
else
  IFS='|' read -r slot_name slot_type slot_active restart_lsn wal_status safe_wal_size <<< "${primary_slot}"
  info "primary slot=${slot_name:-<empty>} type=${slot_type:-<empty>} active=${slot_active:-<empty>} restart_lsn=${restart_lsn:-<empty>} wal_status=${wal_status:-<empty>} safe_wal_size=${safe_wal_size:-<empty>}"
  if [[ "${slot_type}" == "physical" ]]; then
    ok "primary slot is physical"
  else
    fail "primary slot type is ${slot_type:-<empty>}, expected physical"
  fi
  if [[ "${slot_active}" == "true" || "${slot_active}" == "t" ]]; then
    ok "primary slot is active"
  else
    fail "primary slot is inactive"
  fi
  case "${wal_status}" in
    reserved|extended|unreserved) ok "primary slot wal_status=${wal_status}" ;;
    *) warn "primary slot wal_status=${wal_status:-<empty>}" ;;
  esac
fi

standby_recovery="$(
  run_remote_sql "${STANDBY_SSH}" "${STANDBY_PROJECT_DIR}" "${STANDBY_COMPOSE_FILE}" "${STANDBY_DB_SERVICE}" \
    "select pg_is_in_recovery();"
)"
if [[ "${standby_recovery}" == "t" ]]; then
  ok "standby database is in recovery"
else
  fail "standby database should be in recovery; got ${standby_recovery:-<empty>}"
fi

standby_receiver_sql="
select
  coalesce(status, ''),
  coalesce(sender_host, ''),
  coalesce(sender_port::text, ''),
  coalesce(slot_name, ''),
  coalesce(latest_end_lsn::text, ''),
  coalesce(extract(epoch from now() - latest_end_time)::bigint::text, '')
from pg_stat_wal_receiver;
"
standby_receiver="$(
  run_remote_sql "${STANDBY_SSH}" "${STANDBY_PROJECT_DIR}" "${STANDBY_COMPOSE_FILE}" "${STANDBY_DB_SERVICE}" \
    "${standby_receiver_sql}"
)"
if [[ -z "${standby_receiver}" ]]; then
  fail "standby has no pg_stat_wal_receiver row"
else
  IFS='|' read -r receiver_status sender_host sender_port receiver_slot latest_end_lsn latest_end_age_seconds <<< "${standby_receiver}"
  info "standby receiver status=${receiver_status:-<empty>} sender=${sender_host:-<empty>}:${sender_port:-<empty>} slot=${receiver_slot:-<empty>} latest_end_lsn=${latest_end_lsn:-<empty>} latest_end_age_seconds=${latest_end_age_seconds:-<empty>}"
  if [[ "${receiver_status}" == "streaming" ]]; then
    ok "standby WAL receiver is streaming"
  else
    fail "standby WAL receiver status is ${receiver_status:-<empty>}, expected streaming"
  fi
  if [[ "${receiver_slot}" == "${EXPECTED_SLOT}" ]]; then
    ok "standby uses expected slot ${EXPECTED_SLOT}"
  else
    fail "standby receiver slot is ${receiver_slot:-<empty>}, expected ${EXPECTED_SLOT}"
  fi
  if [[ -n "${EXPECTED_PRIMARY_WG_IP}" && "${sender_host}" != "${EXPECTED_PRIMARY_WG_IP}" ]]; then
    fail "standby receiver sender_host=${sender_host:-<empty>}, expected ${EXPECTED_PRIMARY_WG_IP}"
  fi
fi

if (( failures > 0 )); then
  log summary "status=failed failures=${failures} warnings=${warnings}"
  exit 1
fi

log summary "status=passed failures=0 warnings=${warnings}"
