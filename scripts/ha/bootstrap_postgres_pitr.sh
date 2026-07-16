#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="${PROJECT_DIR:-}"
COMPOSE_FILE="${COMPOSE_FILE:-}"
APP_SERVICE="${APP_SERVICE:-app}"
DB_SERVICE="${DB_SERVICE:-db}"
ENV_INPUT_FILE="${ENV_INPUT_FILE:-}"
PITR_REQUIRED="${PITR_REQUIRED:-true}"
PITR_SYSTEMD_ENV_FILE="${PITR_SYSTEMD_ENV_FILE:-/etc/mvn-postgres-pitr.env}"
PITR_SYSTEMD_UNIT_DIR="${PITR_SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
CONFIGURE_HELPER="${CONFIGURE_HELPER:-/usr/local/sbin/mvn-postgres-pitr-configure-env}"
PROVISION_HELPER="${PROVISION_HELPER:-/usr/local/sbin/mvn-postgres-pitr-provision-host}"
BASEBACKUP_HELPER="${BASEBACKUP_HELPER:-/usr/local/sbin/mvn-postgres-pitr-basebackup}"
WAL_UPLOAD_HELPER="${WAL_UPLOAD_HELPER:-/usr/local/sbin/mvn-postgres-pitr-upload-wal}"
STATUS_HELPER="${STATUS_HELPER:-/usr/local/sbin/mvn-postgres-pitr-status}"
RESTORE_DRILL_HELPER="${RESTORE_DRILL_HELPER:-/usr/local/sbin/mvn-postgres-pitr-restore-drill}"
RUNTIME_CHECK_HELPER="${RUNTIME_CHECK_HELPER:-/usr/local/sbin/mvn-postgres-pitr-runtime-check}"
TOOL_RUNNER_HELPER="${TOOL_RUNNER_HELPER:-/usr/local/sbin/mvn-postgres-pitr-tool-runner}"
BLUE_GREEN_HELPER="${BLUE_GREEN_HELPER:-/usr/local/libexec/mvn-pitr/deploy_backend_blue_green.sh}"
BLUE_GREEN_SAFETY_HELPER="${API_BLUE_GREEN_SAFETY_HELPER:-/usr/local/libexec/mvn-pitr/deploy_backend_blue_green_safety.sh}"
DEPLOY_LOCK_HELPER="${API_DEPLOY_LOCK_HELPER:-/usr/local/libexec/mvn-pitr/safe_deploy_lock.py}"
DEPLOY_CAPACITY_HELPER="${API_DEPLOY_CAPACITY_HELPER:-/usr/local/libexec/mvn-pitr/require_deploy_capacity.sh}"
PITR_MARKER_VALIDATOR="${API_PITR_MAINTENANCE_MARKER_VALIDATOR:-/usr/local/libexec/mvn-pitr/verify_pitr_maintenance_marker.py}"
DEPLOY_LOCK_HELPER_SHA256="${API_DEPLOY_LOCK_HELPER_SHA256:-}"
DEPLOY_LOCK_FD="${API_DEPLOY_LOCK_FD:-}"
PITR_TRANSACTION_ID="${PITR_TRANSACTION_ID:-${PITR_OPERATION_ID:-}}"
phase="${1:-preflight}"
log() {
  printf '[pitr-bootstrap] %s\n' "$*"
}
die() {
  printf '[pitr-bootstrap][fail] %s\n' "$*" >&2
  exit 1
}
usage() {
  cat <<'EOF'
Usage:
  mvn-postgres-pitr-bootstrap <phase>

Phases:
  preflight                   Validate one legacy node and probe candidate R2 credentials.
  provision-node              Create the fixed root-owned PITR host state for this transaction.
  configure-node              Commit root-only secrets and sanitize this node's project env.
  scrub-node                  Recreate API/bot runtime without PITR secrets and delete old backups.
  basebackup                  Upload an initial physical basebackup to the private PITR bucket.
  enable-archive-env          Set POSTGRES_PITR_ARCHIVE_MODE=on in PROJECT_DIR/.env.
  activate-archive            Disabled for Patroni; use a reviewed rolling DCS rollout.
  enable-timers               Verify active PITR, then enable recurring timers.
  verify                      Run strict PITR status check.
  restore-drill               Run disposable PITR restore drill.
Required environment for preflight/configure-node:
  ENV_INPUT_FILE=/proc/self/fd/<sealed-memfd>
  PITR_TRANSACTION_ID=<32 lowercase hex characters>

Common environment:
  PROJECT_DIR=<reviewed Patroni node project directory>
  COMPOSE_FILE=docker-compose.patroni.yml
EOF
}
if [[ "${phase}" == "help" || "${phase}" == "--help" || "${phase}" == "-h" ]]; then
  usage
  exit 0
fi
cd_project() {
  [[ -n "${PROJECT_DIR}" ]] || die "PROJECT_DIR must be set explicitly"
  [[ -n "${COMPOSE_FILE}" ]] || die "COMPOSE_FILE must be set explicitly"
  [[ -d "${PROJECT_DIR}" ]] || die "project dir not found: ${PROJECT_DIR}"
  [[ -f "${PROJECT_DIR}/${COMPOSE_FILE}" ]] || die "compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}"
  cd "${PROJECT_DIR}"
}
compose() {
  docker compose -f "${COMPOSE_FILE}" "$@"
}
require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}
require_executable() {
  [[ -x "$1" ]] || die "required helper is not executable: $1"
}
require_active_patroni_compose() {
  local db_container managed_configs runtime_policy target_config
  runtime_policy="${1:-operational}"
  [[ "${COMPOSE_FILE}" == "docker-compose.patroni.yml" ]] ||
    die "refusing non-Patroni compose file: ${COMPOSE_FILE:-<empty>}"
  cd_project
  require_command docker
  [[ "${DOCKER_CONTEXT:-}" == "default" ]] ||
    die "DOCKER_CONTEXT must be the local default context"
  docker compose version >/dev/null 2>&1 || die "docker compose is not available"
  require_executable "${RUNTIME_CHECK_HELPER}"
  if [[ "${runtime_policy}" == "legacy-or-clean" ]]; then
    if BACKEND_IMAGE="$(
      "${RUNTIME_CHECK_HELPER}" \
        --project-dir "${PROJECT_DIR}" \
        --compose-file "${COMPOSE_FILE}" \
        --pitr-env-policy legacy-migration 2>/dev/null
    )"; then
      runtime_policy=legacy-migration
    elif BACKEND_IMAGE="$(
      "${RUNTIME_CHECK_HELPER}" \
        --project-dir "${PROJECT_DIR}" \
        --compose-file "${COMPOSE_FILE}" \
        --pitr-env-policy migration-files-clean 2>/dev/null
    )"; then
      runtime_policy=migration-files-clean
    elif BACKEND_IMAGE="$(
      "${RUNTIME_CHECK_HELPER}" \
        --project-dir "${PROJECT_DIR}" \
        --compose-file "${COMPOSE_FILE}" \
        --pitr-env-policy configured
    )"; then
      runtime_policy=configured
    else
      die "PITR runtime contract is neither reviewed legacy nor migration-files-clean"
    fi
  else
    BACKEND_IMAGE="$(
      "${RUNTIME_CHECK_HELPER}" \
        --project-dir "${PROJECT_DIR}" \
        --compose-file "${COMPOSE_FILE}" \
        --pitr-env-policy "${runtime_policy}"
    )" || die "PITR runtime contract failed"
  fi
  export BACKEND_IMAGE
  db_container="$(compose ps -q "${DB_SERVICE}")"
  [[ -n "${db_container}" ]] || die "managed ${DB_SERVICE} container is not running"
  managed_configs="$(
    docker inspect \
      --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' \
      "${db_container}" 2>/dev/null || true
  )"
  target_config="$(cd "$(dirname "${PROJECT_DIR}/${COMPOSE_FILE}")" && pwd -P)/$(basename "${COMPOSE_FILE}")"
  [[ "${managed_configs}" == "${target_config}" ]] ||
    die "running ${DB_SERVICE} container is not managed only by ${target_config}"
}

require_root_for_write_phase() {
  if [[ "$(id -u)" -ne 0 ]]; then
    die "run this phase as root on the current PostgreSQL primary host"
  fi
}

require_primary_db() {
  local in_recovery
  in_recovery="$(read_in_recovery)"
  if [[ "${in_recovery}" != "f" ]]; then
    die "refusing PITR bootstrap: ${DB_SERVICE} is not the writable primary; pg_is_in_recovery=${in_recovery:-<empty>}"
  fi
  log "db is writable primary"
}

read_in_recovery() {
  compose exec -T "${DB_SERVICE}" sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -Atqc "SELECT pg_is_in_recovery()"' 2>/dev/null || true
}

require_archive_active() {
  local archive_mode archive_timeout archive_command expected_command
  archive_mode="$(compose exec -T "${DB_SERVICE}" sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -Atqc "SELECT setting FROM pg_settings WHERE name = '\''archive_mode'\''"' 2>/dev/null || true)"
  archive_timeout="$(compose exec -T "${DB_SERVICE}" sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -Atqc "SELECT setting FROM pg_settings WHERE name = '\''archive_timeout'\''"' 2>/dev/null || true)"
  archive_command="$(compose exec -T "${DB_SERVICE}" sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -Atqc "SELECT setting FROM pg_settings WHERE name = '\''archive_command'\''"' 2>/dev/null || true)"
  expected_command='/usr/local/bin/mvn-patroni-archive-wal "%p" "%f"'
  [[ "${archive_mode}" == "on" ]] || die "archive_mode is not active"
  [[ "${archive_timeout}" == "300" ]] ||
    die "archive_timeout does not match the reviewed 300 seconds"
  [[ "${archive_command}" == "${expected_command}" ]] ||
    die "archive_command does not match the reviewed Patroni command"
  log "active Patroni archive settings verified"
}

require_timer_runtime_contract() {
  local actual drop_ins expected expected_exec expected_stop expected_timeout fragment mode need_reload owner service unit_file
  [[ -f "${PITR_SYSTEMD_ENV_FILE}" && ! -L "${PITR_SYSTEMD_ENV_FILE}" ]] ||
    die "PITR systemd env must be a regular non-symlink file"
  owner="$(stat -c '%u' "${PITR_SYSTEMD_ENV_FILE}" 2>/dev/null || stat -f '%u' "${PITR_SYSTEMD_ENV_FILE}")"
  mode="$(stat -c '%a' "${PITR_SYSTEMD_ENV_FILE}" 2>/dev/null || stat -f '%Lp' "${PITR_SYSTEMD_ENV_FILE}")"
  [[ "${owner}" == "0" ]] || die "PITR systemd env must be owned by root"
  [[ "${mode}" == "600" ]] || die "PITR systemd env mode must be exactly 600"
  expected="$(printf 'PROJECT_DIR=%s\nCOMPOSE_FILE=%s' "${PROJECT_DIR}" "${COMPOSE_FILE}")"
  actual="$(cat "${PITR_SYSTEMD_ENV_FILE}")"
  [[ "${actual}" == "${expected}" ]] ||
    die "PITR systemd env does not match the selected Patroni node"

  for service in \
    mvn-postgres-wal-upload.service \
    mvn-postgres-wal-upload.timer \
    mvn-postgres-basebackup.service \
    mvn-postgres-basebackup.timer; do
    unit_file="${PITR_SYSTEMD_UNIT_DIR}/${service}"
    [[ -f "${unit_file}" && ! -L "${unit_file}" ]] ||
      die "required PITR unit is missing or unsafe: ${unit_file}"
    fragment="$(systemctl show --property=FragmentPath --value "${service}" 2>/dev/null || true)"
    [[ "${fragment}" == "${unit_file}" ]] ||
      die "${service} is not loaded from the reviewed unit file"
    drop_ins="$(systemctl show --property=DropInPaths --value "${service}" 2>/dev/null || true)"
    [[ -z "${drop_ins}" ]] || die "${service} has unreviewed systemd drop-ins"
    need_reload="$(systemctl show --property=NeedDaemonReload --value "${service}" 2>/dev/null || true)"
    [[ "${need_reload}" == "no" ]] ||
      die "${service} has not loaded the reviewed unit generation"
    if [[ "${service}" == *.service ]]; then
      grep -Fxq "EnvironmentFile=${PITR_SYSTEMD_ENV_FILE}" "${unit_file}" ||
        die "${service} must require the exact PITR systemd env"
      if grep -Eq '^Environment=(PROJECT_DIR|COMPOSE_FILE)=' "${unit_file}"; then
        die "${service} contains a fail-open project or compose default"
      fi
      case "${service}" in
        mvn-postgres-wal-upload.service)
          expected_exec='/usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LANG=C LC_ALL=C /usr/bin/python3 -I /usr/local/sbin/mvn-postgres-pitr-scheduled-runner --phase wal-upload --project-dir ${PROJECT_DIR} --compose-file ${COMPOSE_FILE}'
          expected_timeout='15min'
          expected_stop='30s'
          expected_collision='skip'
          ;;
        mvn-postgres-basebackup.service)
          expected_exec='/usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LANG=C LC_ALL=C /usr/bin/python3 -I /usr/local/sbin/mvn-postgres-pitr-scheduled-runner --phase basebackup --project-dir ${PROJECT_DIR} --compose-file ${COMPOSE_FILE}'
          expected_timeout='2h'
          expected_stop='2min'
          expected_collision='retry'
          ;;
      esac
      grep -Fxq "ExecStart=${expected_exec}" "${unit_file}" ||
        die "${service} does not use the reviewed clean execution environment"
      if [[ "${expected_collision}" == "skip" ]]; then
        grep -Fxq "SuccessExitStatus=75" "${unit_file}" ||
          die "${service} must treat a lock collision as an intentional skip"
      else
        ! grep -Eq '^SuccessExitStatus=.*75' "${unit_file}" ||
          die "${service} must not accept a skipped daily backup"
        grep -Fxq "Restart=on-failure" "${unit_file}" ||
          die "${service} must retry a lock collision"
        grep -Fxq "RestartSec=5min" "${unit_file}" ||
          die "${service} must use the reviewed retry interval"
      fi
      grep -Fxq "TimeoutStartSec=${expected_timeout}" "${unit_file}" ||
        die "${service} does not have the reviewed execution timeout"
      grep -Fxq "TimeoutStopSec=${expected_stop}" "${unit_file}" ||
        die "${service} does not have the reviewed stop timeout"
      grep -Fxq "KillMode=control-group" "${unit_file}" ||
        die "${service} must terminate the complete scheduled job group"
    fi
  done
  log "PITR systemd environment and unit contract verified"
}

require_env_input_file() {
  [[ -n "${ENV_INPUT_FILE}" ]] || die "ENV_INPUT_FILE is required for this phase"
  [[ -f "${ENV_INPUT_FILE}" ]] || die "ENV_INPUT_FILE not found: ${ENV_INPUT_FILE}"

  local mode
  mode="$(stat -c '%a' "${ENV_INPUT_FILE}")"
  if (( (8#${mode} & 8#077) != 0 )); then
    die "ENV_INPUT_FILE must not be readable by group/other; run chmod 600 ${ENV_INPUT_FILE}"
  fi
}

require_transaction_id() {
  [[ "${PITR_TRANSACTION_ID}" =~ ^[0-9a-f]{32}$ ]] ||
    die "PITR_TRANSACTION_ID must be exactly 32 lowercase hex characters"
}

reviewed_node_alias() {
  case "${PROJECT_DIR}" in
    /opt/air-api) printf 'mvn-api\n' ;;
    /opt/mvn-reserve) printf 'zakup\n' ;;
    *) die "project directory is not a reviewed Patroni node" ;;
  esac
}

print_archive_settings() {
  compose exec -T "${DB_SERVICE}" sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -AtF "|"' <<'SQL' |
select name, setting
from pg_settings
where name in ('archive_mode', 'archive_timeout', 'archive_command')
order by name;
SQL
  while IFS='|' read -r name setting; do
    log "${name}=${setting}"
  done
}

preflight() {
  local node_alias
  require_root_for_write_phase
  require_transaction_id
  require_active_patroni_compose legacy-or-clean
  require_archive_active
  require_executable "${CONFIGURE_HELPER}"
  require_executable "${BASEBACKUP_HELPER}"
  require_executable "${WAL_UPLOAD_HELPER}"
  require_executable "${STATUS_HELPER}"
  require_executable "${RESTORE_DRILL_HELPER}"
  require_executable "${RUNTIME_CHECK_HELPER}"
  require_executable "${TOOL_RUNNER_HELPER}"
  print_archive_settings
  require_env_input_file
  log "validating PITR input env with dry-run configure helper"
  "${CONFIGURE_HELPER}" \
    --project-dir "${PROJECT_DIR}" \
    --input-env-file "${ENV_INPUT_FILE}" \
    --transaction-id "${PITR_TRANSACTION_ID}" \
    --dry-run
  node_alias="$(reviewed_node_alias)"
  "${TOOL_RUNNER_HELPER}" \
    --phase credential-probe \
    --transaction-id "${PITR_TRANSACTION_ID}" \
    --node "${node_alias}"
  log "candidate R2 credentials passed put/head/get/delete probe"
}

provision_node() {
  require_root_for_write_phase
  require_transaction_id
  require_active_patroni_compose legacy-or-clean
  require_executable "${PROVISION_HELPER}"
  "${PROVISION_HELPER}" \
    --project-dir "${PROJECT_DIR}" \
    --compose-file "${COMPOSE_FILE}" \
    --transaction-id "${PITR_TRANSACTION_ID}"
  log "transactional PITR host state provisioned and recurring units remain quiesced"
}

configure_node() {
  local node_alias
  require_root_for_write_phase
  require_transaction_id
  require_active_patroni_compose legacy-or-clean
  require_env_input_file
  node_alias="$(reviewed_node_alias)"
  "${CONFIGURE_HELPER}" \
    --project-dir "${PROJECT_DIR}" \
    --input-env-file "${ENV_INPUT_FILE}" \
    --root-transaction-id "${PITR_TRANSACTION_ID}" \
    --transaction-node "${node_alias}" \
    --transaction-stage configure-node \
    --enable-archive
  require_active_patroni_compose migration-files-clean
  log "root-only PITR secrets committed and final archive env staged"
}

write_role_file() {
  local path="$1" value="$2" temporary
  temporary="$(mktemp "${path}.pitr.XXXXXX")"
  printf '%s\n' "${value}" >"${temporary}"
  chown root:root "${temporary}"
  chmod 600 "${temporary}"
  mv -f "${temporary}" "${path}"
}

remove_service_all_states() {
  local service="$1"
  compose --profile bluegreen rm --stop --force "${service}" >/dev/null 2>&1 || true
  if [[ -n "$(compose --profile bluegreen ps --all -q "${service}")" ]]; then
    die "could not remove stale ${service} containers"
  fi
}

scrub_legacy_secret_backups() {
  /usr/bin/python3 -I - "${PROJECT_DIR}" <<'PY'
import os
import re
import stat
import sys
from pathlib import Path

project = Path(sys.argv[1])
if project not in {Path("/opt/air-api"), Path("/opt/mvn-reserve")}:
    raise SystemExit("unreviewed PITR scrub project")
patterns = (
    (project, re.compile(r"^\.env\.bak-(?:pitr|patroni-pitr)-[A-Za-z0-9_.:-]+$")),
    (Path("/etc"), re.compile(r"^mvn-postgres-pitr(?:\.secrets)?\.env\.bak-patroni-[A-Za-z0-9_.:-]+$")),
)
targets = []
for directory, pattern in patterns:
    for path in directory.iterdir():
        if pattern.fullmatch(path.name):
            targets.append(path)
legacy_input = Path("/root/mvn-postgres-pitr.env")
if legacy_input.exists() or legacy_input.is_symlink():
    targets.append(legacy_input)
for path in targets:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise SystemExit(f"unsafe legacy PITR secret backup: {path}")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise SystemExit(f"legacy PITR secret backup changed: {path}")
    finally:
        os.close(descriptor)
    path.unlink()
for directory in {path.parent for path in targets}:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
PY
}

scrub_node() {
  local active_service capacity_profile=primary in_recovery proxy_mode slot
  require_root_for_write_phase
  require_transaction_id
  if BACKEND_IMAGE="$(
    "${RUNTIME_CHECK_HELPER}" \
      --project-dir "${PROJECT_DIR}" \
      --compose-file "${COMPOSE_FILE}" \
      --pitr-env-policy configured 2>/dev/null
  )"; then
    export BACKEND_IMAGE
    require_active_patroni_compose configured
    scrub_legacy_secret_backups
    log "node runtime is already configured and legacy PITR backups are absent"
    return
  fi
  require_active_patroni_compose migration-files-clean
  in_recovery="$(read_in_recovery)"
  case "${in_recovery}" in
    f)
      [[ "${BLUE_GREEN_HELPER}" == "/usr/local/libexec/mvn-pitr/deploy_backend_blue_green.sh" ]] ||
        die "unreviewed PITR blue-green helper path"
      [[ "${DEPLOY_LOCK_FD}" == "9" ]] ||
        die "PITR scrub requires inherited deployment lock fd 9"
      [[ "${PITR_MARKER_VALIDATOR}" == "/usr/local/libexec/mvn-pitr/verify_pitr_maintenance_marker.py" ]] ||
        die "unreviewed PITR maintenance marker validator path"
      [[ "${DEPLOY_LOCK_HELPER_SHA256}" =~ ^[0-9a-f]{64}$ ]] ||
        die "PITR deploy-lock helper digest is missing"
      python3 "${PITR_MARKER_VALIDATOR}" runtime \
        "${BLUE_GREEN_HELPER}" "${DEPLOY_LOCK_HELPER}" \
        "${BLUE_GREEN_SAFETY_HELPER}" "${DEPLOY_CAPACITY_HELPER}" ||
        die "unreviewed PITR scrub runtime helpers"
      python3 "${DEPLOY_LOCK_HELPER}" verify \
        "${PROJECT_DIR}/.deploy.lock" "${DEPLOY_LOCK_FD}" ||
        die "PITR inherited deployment lock verification failed"
      curl -fsS --max-time 5 http://127.0.0.1:8008/leader >/dev/null ||
        die "local Patroni node does not hold the DCS leader lock"
      proxy_mode=host_nginx
      if [[ "${PROJECT_DIR}" == "/opt/mvn-reserve" ]]; then
        proxy_mode=container_nginx
        capacity_profile=reserve
      fi
      API_PROJECT_DIR="${PROJECT_DIR}" \
        API_COMPOSE_FILE="${COMPOSE_FILE}" \
        API_PROXY_MODE="${proxy_mode}" \
        API_NGINX_UPSTREAM_FILE="${PROJECT_DIR}/api-proxy/upstream.conf" \
        API_PROXY_CONFIG_FILE="${PROJECT_DIR}/api-proxy/nginx.conf" \
        API_LEGACY_PORT=18000 \
        API_INTERNAL_PROXY_PORT=18080 \
        API_PUBLIC_READY_URL=https://api.mvn.by/api/ready \
        API_DEPLOY_LOCK_FD="${DEPLOY_LOCK_FD}" \
        API_DEPLOY_LOCK_FILE="${PROJECT_DIR}/.deploy.lock" \
        API_DEPLOY_LOCK_HELPER="${DEPLOY_LOCK_HELPER}" \
        API_DEPLOY_LOCK_HELPER_SHA256="${DEPLOY_LOCK_HELPER_SHA256}" \
        API_BLUE_GREEN_SAFETY_HELPER="${BLUE_GREEN_SAFETY_HELPER}" \
        API_DEPLOY_CAPACITY_HELPER="${DEPLOY_CAPACITY_HELPER}" \
        API_DEPLOY_CAPACITY_PROFILE="${capacity_profile}" \
        API_PITR_MAINTENANCE_MARKER_VALIDATOR="${PITR_MARKER_VALIDATOR}" \
        API_PITR_MAINTENANCE_TRANSACTION_ID="${PITR_TRANSACTION_ID}" \
        API_BLUE_GREEN_SUMMARY_FILE=/dev/null \
        API_RUN_MIGRATIONS=false \
        API_RUN_DEFAULTS=false \
        API_FORCE_ACTIVATION=true \
        GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT=/usr/local/libexec/mvn-pitr/prepare_google_oauth_token_dir.sh \
        BACKEND_IMAGE="${BACKEND_IMAGE}" \
        bash "${BLUE_GREEN_HELPER}"
      curl -fsS --max-time 5 http://127.0.0.1:8008/leader >/dev/null ||
        die "Patroni leader lock changed during primary runtime scrub"
      slot="$(tr -d '\r\n' < "${PROJECT_DIR}/.active-api-slot")"
      case "${slot}" in
        blue) active_service=app-blue ;;
        green) active_service=app-green ;;
        *) die "primary scrub did not produce a reviewed active API slot" ;;
      esac
      for service in app app-blue app-green; do
        if [[ "${service}" != "${active_service}" ]]; then
          remove_service_all_states "${service}"
        fi
      done
      ;;
    t)
      write_role_file "${PROJECT_DIR}/.ha-app-role.env" "HA_APP_ROLE=standby"
      write_role_file "${PROJECT_DIR}/.ha-bot-role.env" "HA_BOT_ROLE=standby"
      remove_service_all_states bot
      slot="$(tr -d '\r\n' < "${PROJECT_DIR}/.active-api-slot" 2>/dev/null || true)"
      case "${slot}" in
        blue) active_service=app-blue ;;
        green) active_service=app-green ;;
        '') active_service=app ;;
        *) die "standby active API slot is invalid" ;;
      esac
      export BACKEND_IMAGE
      compose --profile bluegreen up -d --no-deps --force-recreate "${active_service}"
      for service in app app-blue app-green; do
        if [[ "${service}" != "${active_service}" ]]; then
          remove_service_all_states "${service}"
        fi
      done
      ;;
    *) die "could not determine PostgreSQL recovery state during node scrub" ;;
  esac
  scrub_legacy_secret_backups
  require_active_patroni_compose configured
  log "API/bot runtime and legacy PITR secret backups are clean"
}

basebackup() {
  require_root_for_write_phase
  require_active_patroni_compose configured
  require_primary_db
  PROJECT_DIR="${PROJECT_DIR}" COMPOSE_FILE="${COMPOSE_FILE}" APP_SERVICE="${APP_SERVICE}" DB_SERVICE="${DB_SERVICE}" \
    PITR_RUNTIME_POLICY=configured \
    "${BASEBACKUP_HELPER}"
}

enable_archive_env() {
  local node_alias
  require_root_for_write_phase
  require_transaction_id
  require_active_patroni_compose configured
  node_alias="$(reviewed_node_alias)"
  "${CONFIGURE_HELPER}" \
    --project-dir "${PROJECT_DIR}" \
    --root-transaction-id "${PITR_TRANSACTION_ID}" \
    --transaction-node "${node_alias}" \
    --transaction-stage enable-archive \
    --enable-archive
  log "PITR archive env staged on the reviewed Patroni node"
}

activate_archive() {
  die "activate-archive is disabled for Patroni; use a reviewed DCS update and rolling restart"
}

enable_timers() {
  local failure_reason rollback_failed service timer
  local index
  local -a timers=(
    mvn-postgres-wal-upload.timer
    mvn-postgres-basebackup.timer
  )
  local -a was_active=()
  local -a was_enabled=()
  local -a services=(
    mvn-postgres-wal-upload.service
    mvn-postgres-basebackup.service
  )
  local -a was_service_active=()
  require_root_for_write_phase
  require_active_patroni_compose
  require_primary_db
  require_archive_active
  require_command systemctl
  systemctl daemon-reload
  require_timer_runtime_contract
  for index in "${!timers[@]}"; do
    timer="${timers[index]}"
    was_active[index]="$(systemctl is-active "${timer}" 2>/dev/null || true)"
    case "${was_active[index]}" in
      active|inactive) ;;
      *) die "could not determine exact active state for ${timer}" ;;
    esac
    was_enabled[index]="$(systemctl is-enabled "${timer}" 2>/dev/null || true)"
    case "${was_enabled[index]}" in
      enabled|disabled) ;;
      *) die "could not determine exact enabled state for ${timer}" ;;
    esac
  done
  for index in "${!services[@]}"; do
    service="${services[index]}"
    was_service_active[index]="$(systemctl is-active "${service}" 2>/dev/null || true)"
    case "${was_service_active[index]}" in
      active|inactive) ;;
      *) die "could not determine safe initial service state for ${service}" ;;
    esac
  done
  failure_reason=""
  if ! systemctl enable --now "${timers[@]}"; then
    failure_reason="timer enable failed"
  elif ! PITR_REQUIRED=true PROJECT_DIR="${PROJECT_DIR}" COMPOSE_FILE="${COMPOSE_FILE}" \
    APP_SERVICE="${APP_SERVICE}" DB_SERVICE="${DB_SERVICE}" "${STATUS_HELPER}"; then
    failure_reason="strict PITR verification failed"
  fi
  if [[ -n "${failure_reason}" ]]; then
    rollback_failed=false
    for service in "${services[@]}"; do
      systemctl stop "${service}" || rollback_failed=true
    done
    for index in "${!timers[@]}"; do
      timer="${timers[index]}"
      if [[ "${was_enabled[index]}" == "enabled" ]]; then
        systemctl enable "${timer}" || rollback_failed=true
      else
        systemctl disable "${timer}" || rollback_failed=true
      fi
      if [[ "${was_active[index]}" == "active" ]]; then
        systemctl start "${timer}" || rollback_failed=true
      else
        systemctl stop "${timer}" || rollback_failed=true
      fi
    done
    for index in "${!services[@]}"; do
      service="${services[index]}"
      if [[ "${was_service_active[index]}" == "active" ]]; then
        systemctl start "${service}" || rollback_failed=true
      else
        systemctl stop "${service}" || rollback_failed=true
      fi
    done
    if [[ "${rollback_failed}" == "true" ]]; then
      die "${failure_reason}; restoring the previous timer state also failed"
    fi
    die "${failure_reason}; previous timer state was restored"
  fi
  systemctl list-timers --all 'mvn-postgres*' --no-pager
}

verify() {
  require_active_patroni_compose
  require_primary_db
  require_archive_active
  require_command systemctl
  require_timer_runtime_contract
  PITR_REQUIRED="${PITR_REQUIRED}" PROJECT_DIR="${PROJECT_DIR}" COMPOSE_FILE="${COMPOSE_FILE}" APP_SERVICE="${APP_SERVICE}" DB_SERVICE="${DB_SERVICE}" \
    "${STATUS_HELPER}"
}

restore_drill() {
  require_root_for_write_phase
  require_active_patroni_compose
  require_primary_db
  require_archive_active
  PROJECT_DIR="${PROJECT_DIR}" COMPOSE_FILE="${COMPOSE_FILE}" APP_SERVICE="${APP_SERVICE}" DB_SERVICE="${DB_SERVICE}" \
    "${RESTORE_DRILL_HELPER}"
}

case "${phase}" in
  preflight)
    preflight
    ;;
  provision-node)
    provision_node
    ;;
  configure-node)
    configure_node
    ;;
  scrub-node)
    scrub_node
    ;;
  basebackup)
    basebackup
    ;;
  enable-archive-env)
    enable_archive_env
    ;;
  activate-archive)
    activate_archive
    ;;
  enable-timers)
    enable_timers
    ;;
  verify)
    verify
    ;;
  restore-drill)
    restore_drill
    ;;
  configure-env|bootstrap-before-maintenance)
    die "legacy combined PITR phases are disabled; use the cluster transaction controller"
    ;;
  *)
    usage >&2
    die "unknown phase: ${phase}"
    ;;
esac
