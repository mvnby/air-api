#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
APP_SERVICE="${APP_SERVICE:-app}"
DB_SERVICE="${DB_SERVICE:-db}"
ENV_INPUT_FILE="${ENV_INPUT_FILE:-}"
CONFIRM_RECREATE_DB="${CONFIRM_RECREATE_DB:-false}"
POST_RECREATE_SERVICES="${POST_RECREATE_SERVICES:-app bot}"
PITR_REQUIRED="${PITR_REQUIRED:-true}"

CONFIGURE_HELPER="${CONFIGURE_HELPER:-/usr/local/sbin/mvn-postgres-pitr-configure-env}"
BASEBACKUP_HELPER="${BASEBACKUP_HELPER:-/usr/local/sbin/mvn-postgres-pitr-basebackup}"
WAL_UPLOAD_HELPER="${WAL_UPLOAD_HELPER:-/usr/local/sbin/mvn-postgres-pitr-upload-wal}"
STATUS_HELPER="${STATUS_HELPER:-/usr/local/sbin/mvn-postgres-pitr-status}"
RESTORE_DRILL_HELPER="${RESTORE_DRILL_HELPER:-/usr/local/sbin/mvn-postgres-pitr-restore-drill}"

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
  preflight                   Validate host, compose, helpers, and optional input env.
  configure-env               Write POSTGRES_PITR_* values into PROJECT_DIR/.env with archive off.
  basebackup                  Upload an initial physical basebackup to the private PITR bucket.
  enable-archive-env          Set POSTGRES_PITR_ARCHIVE_MODE=on in PROJECT_DIR/.env.
  activate-archive            Recreate db, reset archiver counters, switch WAL, and upload WAL.
                              Requires CONFIRM_RECREATE_DB=true.
  enable-timers               Enable recurring WAL upload and basebackup timers.
  verify                      Run strict PITR status check.
  restore-drill               Run disposable PITR restore drill.
  bootstrap-before-maintenance
                              preflight + configure-env + basebackup + enable-archive-env.
                              Does not recreate db.

Required environment for configure-env/bootstrap-before-maintenance:
  ENV_INPUT_FILE=/root/mvn-postgres-pitr.env

Common environment:
  PROJECT_DIR=/opt/air-api
  COMPOSE_FILE=docker-compose.prod.yml
EOF
}

if [[ "${phase}" == "help" || "${phase}" == "--help" || "${phase}" == "-h" ]]; then
  usage
  exit 0
fi

cd_project() {
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

wait_primary_db() {
  local attempt in_recovery
  for attempt in {1..60}; do
    in_recovery="$(read_in_recovery)"
    if [[ "${in_recovery}" == "f" ]]; then
      log "db is writable primary"
      return 0
    fi
    sleep 2
  done
  die "db did not become writable primary after recreate; pg_is_in_recovery=${in_recovery:-<empty>}"
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
  cd_project
  require_command docker
  docker compose version >/dev/null 2>&1 || die "docker compose is not available"
  require_executable "${CONFIGURE_HELPER}"
  require_executable "${BASEBACKUP_HELPER}"
  require_executable "${WAL_UPLOAD_HELPER}"
  require_executable "${STATUS_HELPER}"
  require_executable "${RESTORE_DRILL_HELPER}"
  require_primary_db
  print_archive_settings

  if [[ -n "${ENV_INPUT_FILE}" ]]; then
    require_env_input_file
    log "validating PITR input env with dry-run configure helper"
    local dry_run_log
    dry_run_log="$(mktemp)"
    "${CONFIGURE_HELPER}" \
      --project-dir "${PROJECT_DIR}" \
      --input-env-file "${ENV_INPUT_FILE}" \
      --dry-run >"${dry_run_log}"
    sed -E 's/(secret_values.: .)[^,}]*/\1redacted/g' "${dry_run_log}"
    rm -f "${dry_run_log}"
  else
    log "ENV_INPUT_FILE not set; skipped private bucket credential validation"
  fi
}

configure_env() {
  require_root_for_write_phase
  cd_project
  require_env_input_file
  require_primary_db
  "${CONFIGURE_HELPER}" \
    --project-dir "${PROJECT_DIR}" \
    --input-env-file "${ENV_INPUT_FILE}"
  log "PITR env written with archive mode off"
}

basebackup() {
  require_root_for_write_phase
  cd_project
  require_primary_db
  PROJECT_DIR="${PROJECT_DIR}" COMPOSE_FILE="${COMPOSE_FILE}" APP_SERVICE="${APP_SERVICE}" DB_SERVICE="${DB_SERVICE}" \
    "${BASEBACKUP_HELPER}"
}

enable_archive_env() {
  require_root_for_write_phase
  cd_project
  require_primary_db
  "${CONFIGURE_HELPER}" \
    --project-dir "${PROJECT_DIR}" \
    --enable-archive
  log "PITR archive env enabled; db recreate is still required before archive_mode changes"
}

activate_archive() {
  require_root_for_write_phase
  [[ "${CONFIRM_RECREATE_DB}" == "true" ]] || die "set CONFIRM_RECREATE_DB=true to recreate ${DB_SERVICE}"
  cd_project
  require_primary_db

  log "recreating ${DB_SERVICE} so archive_mode and archive_command become active"
  compose up -d --force-recreate "${DB_SERVICE}"
  wait_primary_db
  log "ensuring app services are running after db recreate: ${POST_RECREATE_SERVICES}"
  # shellcheck disable=SC2086
  compose up -d ${POST_RECREATE_SERVICES}

  require_primary_db
  print_archive_settings

  log "resetting historical pg_stat_archiver counters"
  compose exec -T "${DB_SERVICE}" sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -Atqc "select pg_stat_reset_shared('\''archiver'\'')"'

  log "forcing WAL switch"
  compose exec -T "${DB_SERVICE}" sh -lc 'psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -Atqc "select pg_switch_wal()"'

  log "uploading archived WAL once before timers are enabled"
  PROJECT_DIR="${PROJECT_DIR}" COMPOSE_FILE="${COMPOSE_FILE}" APP_SERVICE="${APP_SERVICE}" \
    "${WAL_UPLOAD_HELPER}"
}

enable_timers() {
  require_root_for_write_phase
  require_command systemctl
  systemctl enable --now mvn-postgres-wal-upload.timer mvn-postgres-basebackup.timer
  systemctl list-timers --all 'mvn-postgres*' --no-pager
}

verify() {
  cd_project
  PITR_REQUIRED="${PITR_REQUIRED}" PROJECT_DIR="${PROJECT_DIR}" COMPOSE_FILE="${COMPOSE_FILE}" APP_SERVICE="${APP_SERVICE}" DB_SERVICE="${DB_SERVICE}" \
    "${STATUS_HELPER}"
}

restore_drill() {
  require_root_for_write_phase
  cd_project
  PROJECT_DIR="${PROJECT_DIR}" COMPOSE_FILE="${COMPOSE_FILE}" APP_SERVICE="${APP_SERVICE}" DB_SERVICE="${DB_SERVICE}" \
    "${RESTORE_DRILL_HELPER}"
}

case "${phase}" in
  preflight)
    preflight
    ;;
  configure-env)
    configure_env
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
  bootstrap-before-maintenance)
    preflight
    configure_env
    basebackup
    enable_archive_env
    log "before-maintenance phase complete; run activate-archive during a short maintenance window"
    ;;
  *)
    usage >&2
    die "unknown phase: ${phase}"
    ;;
esac
