#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="${PROJECT_DIR:-}"
COMPOSE_FILE="${COMPOSE_FILE:-}"
if [[ -z "${PITR_INSTALL_LOCK_FD:-}" ]]; then
  exec /usr/bin/python3 -I \
    "${script_dir}/run_postgres_pitr_install_locked.py" \
    "$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")" \
    "$@"
fi

case "${PITR_INSTALL_LOCK_FD}" in
  ''|*[!0-9]*)
    printf '[pitr-install][fail] invalid inherited lock descriptor\n' >&2
    exit 1
    ;;
esac
command -v flock >/dev/null 2>&1 || {
  printf '[pitr-install][fail] flock is required\n' >&2
  exit 1
}
lock_fd_identity="$(stat -Lc '%d:%i' "/proc/self/fd/${PITR_INSTALL_LOCK_FD}" 2>/dev/null || true)"
lock_path_identity="$(stat -Lc '%d:%i' /run/lock/mvn-postgres-pitr-prerequisites.lock 2>/dev/null || true)"
if [[ -z "${lock_fd_identity}" || "${lock_fd_identity}" != "${lock_path_identity}" ]]; then
  printf '[pitr-install][fail] inherited lock descriptor is not the shared PITR lock\n' >&2
  exit 1
fi
if ! flock -n "${PITR_INSTALL_LOCK_FD}"; then
  printf '[pitr-install][fail] shared PITR lock is not held\n' >&2
  exit 1
fi

case "${PITR_INSTALL_DEPLOY_LOCK_FD:-}" in
  ''|*[!0-9]*)
    printf '[pitr-install][fail] invalid inherited deploy lock descriptor\n' >&2
    exit 1
    ;;
esac
case "${PROJECT_DIR}" in
  /opt/air-api|/opt/mvn-reserve) ;;
  *)
    printf '[pitr-install][fail] unreviewed project directory\n' >&2
    exit 1
    ;;
esac
deploy_fd_identity="$(stat -Lc '%d:%i' "/proc/self/fd/${PITR_INSTALL_DEPLOY_LOCK_FD}" 2>/dev/null || true)"
deploy_path_identity="$(stat -Lc '%d:%i' "${PROJECT_DIR}/.deploy.lock" 2>/dev/null || true)"
if [[ -z "${deploy_fd_identity}" || "${deploy_fd_identity}" != "${deploy_path_identity}" ]]; then
  printf '[pitr-install][fail] inherited deploy lock descriptor is not canonical\n' >&2
  exit 1
fi
if ! flock -n "${PITR_INSTALL_DEPLOY_LOCK_FD}"; then
  printf '[pitr-install][fail] project deploy lock is not held\n' >&2
  exit 1
fi

DB_SERVICE="db"

die() {
  printf '[pitr-install][fail] %s\n' "$*" >&2
  exit 1
}

require_install_quiescence() {
  local role_agent_state timer timer_state unit unit_state
  role_agent_state="$(systemctl is-active mvn-patroni-role-agent.service 2>/dev/null || true)"
  case "${role_agent_state}" in
    inactive|unknown) ;;
    *) die "mvn-patroni-role-agent.service must be inactive during PITR host asset installation" ;;
  esac
  for unit in \
    mvn-postgres-wal-upload.timer \
    mvn-postgres-wal-upload.service \
    mvn-postgres-basebackup.timer \
    mvn-postgres-basebackup.service; do
    unit_state="$(systemctl is-active "${unit}" 2>/dev/null || true)"
    case "${unit_state}" in
      inactive|unknown) ;;
      *) die "${unit} must be inactive before PITR host asset installation" ;;
    esac
  done
  for timer in mvn-postgres-wal-upload.timer mvn-postgres-basebackup.timer; do
    timer_state="$(systemctl is-enabled "${timer}" 2>/dev/null || true)"
    case "${timer_state}" in
      disabled|not-found) ;;
      *) die "${timer} must be disabled before PITR host asset installation" ;;
    esac
  done
}

if [[ "$(id -u)" -ne 0 ]]; then
  die "run as root on a reviewed Patroni host"
fi

if [[ ! -f "scripts/ha/upload_postgres_pitr_to_s3.py" ]]; then
  die "run from the air-api repository root, or copy scripts/ha first"
fi

case "${ENABLE_TIMERS:-false}" in
  false|FALSE|False|0|no|NO|No|off|OFF|Off) ;;
  *) die "installer never enables PITR timers; use the pinned prerequisite helper" ;;
esac

[[ -n "${PROJECT_DIR}" ]] || die "PROJECT_DIR must be set explicitly"
[[ "${COMPOSE_FILE}" == "docker-compose.patroni.yml" ]] ||
  die "COMPOSE_FILE must be docker-compose.patroni.yml"
[[ -d "${PROJECT_DIR}" ]] || die "project dir not found: ${PROJECT_DIR}"
[[ -f "${PROJECT_DIR}/${COMPOSE_FILE}" ]] ||
  die "compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}"
command -v docker >/dev/null 2>&1 || die "docker is required"
docker compose version >/dev/null 2>&1 || die "docker compose is not available"
command -v systemctl >/dev/null 2>&1 || die "systemctl is required"
require_install_quiescence
[[ "${DOCKER_CONTEXT:-}" == "default" ]] || die "DOCKER_CONTEXT must be default"
BACKEND_IMAGE="$(
  /usr/bin/python3 -I scripts/ha/verify_postgres_pitr_runtime.py \
    --project-dir "${PROJECT_DIR}" \
    --compose-file "${COMPOSE_FILE}" \
    --pitr-env-policy runtime-only
)" || die "PITR runtime contract failed"
export BACKEND_IMAGE
db_container="$(cd "${PROJECT_DIR}" && docker compose -f "${COMPOSE_FILE}" ps -q "${DB_SERVICE}")"
[[ -n "${db_container}" ]] || die "managed ${DB_SERVICE} container is not running"
managed_configs="$(
  docker inspect \
    --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' \
    "${db_container}" 2>/dev/null || true
)"
target_config="$(cd "${PROJECT_DIR}" && pwd -P)/${COMPOSE_FILE}"
[[ "${managed_configs}" == "${target_config}" ]] ||
  die "running ${DB_SERVICE} container is not managed only by ${target_config}"

install -o root -g root -m 0755 scripts/ha/upload_postgres_pitr_to_s3.py /usr/local/sbin/mvn-postgres-pitr-upload
install -o root -g root -m 0755 scripts/ha/postgres_pitr_immutable_upload.py /usr/local/sbin/mvn-postgres-pitr-immutable-upload
install -o root -g root -m 0755 scripts/ha/upload_postgres_pitr_wal.sh /usr/local/sbin/mvn-postgres-pitr-upload-wal
install -o root -g root -m 0755 scripts/ha/create_postgres_pitr_basebackup.sh /usr/local/sbin/mvn-postgres-pitr-basebackup
install -o root -g root -m 0755 scripts/ha/configure_postgres_pitr_env.py /usr/local/sbin/mvn-postgres-pitr-configure-env
install -o root -g root -m 0755 scripts/ha/provision_postgres_pitr_host.py /usr/local/sbin/mvn-postgres-pitr-provision-host
install -o root -g root -m 0755 scripts/ha/pitr_config_transaction.py /usr/local/sbin/mvn_postgres_pitr_config_transaction.py
install -o root -g root -m 0755 scripts/ha/restore_postgres_pitr_from_s3.py /usr/local/sbin/mvn-postgres-pitr-restore
install -o root -g root -m 0755 scripts/ha/restore_postgres_pitr_drill.sh /usr/local/sbin/mvn-postgres-pitr-restore-drill
install -o root -g root -m 0755 scripts/ha/check_postgres_pitr_status.sh /usr/local/sbin/mvn-postgres-pitr-status
install -o root -g root -m 0755 scripts/ha/check_postgres_pitr_remote.py /usr/local/sbin/mvn-postgres-pitr-remote-status
install -o root -g root -m 0755 scripts/ha/bootstrap_postgres_pitr.sh /usr/local/sbin/mvn-postgres-pitr-bootstrap
install -o root -g root -m 0755 scripts/ha/verify_postgres_pitr_runtime.py /usr/local/sbin/mvn-postgres-pitr-runtime-check
install -o root -g root -m 0755 scripts/ha/run_postgres_pitr_scheduled.py /usr/local/sbin/mvn-postgres-pitr-scheduled-runner
install -o root -g root -m 0755 scripts/ha/run_postgres_pitr_manual.py /usr/local/sbin/mvn-postgres-pitr-manual-runner
install -o root -g root -m 0755 scripts/ha/calculate_logical_restore_resources.py /usr/local/sbin/mvn-logical-restore-resource-sizer
install -o root -g root -m 0755 scripts/ha/restore_drill_latest_db.sh /usr/local/sbin/mvn-restore-drill-latest-db
install -o root -g root -m 0755 scripts/ha/cleanup_restore_drill_runtime.sh /usr/local/sbin/mvn-restore-drill-latest-db-cleanup
install -o root -g root -m 0755 scripts/ha/run_postgres_pitr_tool.py /usr/local/sbin/mvn-postgres-pitr-tool-runner
install -o root -g root -m 0755 scripts/ha/postgres_pitr_artifact_security.py /usr/local/sbin/mvn-postgres-pitr-artifact-security
install -o root -g root -m 0755 scripts/ha/postgres_pitr_wal_lineage.py /usr/local/sbin/mvn-postgres-pitr-wal-lineage
install -o root -g root -m 0755 scripts/ha/postgres_pitr_recovery_config.py /usr/local/sbin/mvn-postgres-pitr-recovery-config
install -o root -g root -m 0755 scripts/ha/pitr_operation_guard.py /usr/local/sbin/mvn_postgres_pitr_operation_guard.py
install -o root -g root -m 0755 scripts/ha/pitr_operation_cleanup.py /usr/local/sbin/mvn_postgres_pitr_operation_cleanup.py
install -d -o root -g root -m 0755 /usr/local/libexec/mvn-pitr
install -o root -g root -m 0755 scripts/deploy_backend_blue_green.sh /usr/local/libexec/mvn-pitr/deploy_backend_blue_green.sh
install -o root -g root -m 0755 scripts/deploy_backend_blue_green_safety.sh /usr/local/libexec/mvn-pitr/deploy_backend_blue_green_safety.sh
install -o root -g root -m 0755 scripts/ha/require_deploy_capacity.sh /usr/local/libexec/mvn-pitr/require_deploy_capacity.sh
install -o root -g root -m 0755 scripts/ha/verify_pitr_maintenance_marker.py /usr/local/libexec/mvn-pitr/verify_pitr_maintenance_marker.py
install -o root -g root -m 0755 scripts/prepare_google_oauth_token_dir.sh /usr/local/libexec/mvn-pitr/prepare_google_oauth_token_dir.sh
install -o root -g root -m 0755 scripts/ha/safe_deploy_lock.py /usr/local/libexec/mvn-pitr/safe_deploy_lock.py
install -o root -g root -m 0644 deploy/ha/systemd/mvn-postgres-wal-upload.service /etc/systemd/system/mvn-postgres-wal-upload.service
install -o root -g root -m 0644 deploy/ha/systemd/mvn-postgres-wal-upload.timer /etc/systemd/system/mvn-postgres-wal-upload.timer
install -o root -g root -m 0644 deploy/ha/systemd/mvn-postgres-basebackup.service /etc/systemd/system/mvn-postgres-basebackup.service
install -o root -g root -m 0644 deploy/ha/systemd/mvn-postgres-basebackup.timer /etc/systemd/system/mvn-postgres-basebackup.timer

require_install_quiescence
systemctl daemon-reload

echo "Installed PITR assets only. Host state was not provisioned and timers were not enabled."
echo "Complete both reviewed nodes through the cluster transaction documented in docs/api-ha-runbook.md:"
echo "  python3 scripts/ha/apply_postgres_pitr_primary_prerequisites.py --phase migrate-cluster --transaction-id <32-lowercase-hex> --no-prompt"
