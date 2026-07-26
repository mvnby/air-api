#!/usr/bin/env bash
# shellcheck disable=SC2034  # globals are consumed by sourced lifecycle modules
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPERATION="${PATRONI_CANDIDATE_OPERATION:-}"
PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
CANONICAL_FILE="${PATRONI_CANONICAL_COMPOSE_FILE:-${PROJECT_DIR}/docker-compose.patroni.yml}"
CANDIDATE_FILE="${PATRONI_CANDIDATE_COMPOSE_FILE:-}"
CANDIDATE_SOURCE="${PATRONI_CANDIDATE_COMPOSE_SOURCE:-}"
TRANSACTION_SCRIPT="${COMPOSE_CANDIDATE_TRANSACTION_SCRIPT:-/tmp/compose_candidate_transaction.sh}"
MIGRATION_SCRIPT="${PATRONI_MIGRATION_SCRIPT:-/tmp/run_patroni_migrations.sh}"
DEPLOY_SCRIPT="${PATRONI_DEPLOY_SCRIPT:-/tmp/deploy_patroni_api_node.sh}"
ROLE_AGENT_SOURCE="${PATRONI_ROLE_AGENT_SOURCE:-}"
ROLE_AGENT_TARGET="${PATRONI_ROLE_AGENT_TARGET:-/usr/local/sbin/mvn-patroni-role-agent}"
ROLE_COMPOSE_RUNTIME_SOURCE="${PATRONI_ROLE_COMPOSE_RUNTIME_SOURCE:-}"
ROLE_COMPOSE_RUNTIME_TARGET="${PATRONI_ROLE_COMPOSE_RUNTIME_TARGET:-/usr/local/sbin/patroni_compose_runtime.py}"
ROLE_AGENT_CONFIG_SOURCE="${PATRONI_ROLE_AGENT_CONFIG_SOURCE:-}"
ROLE_AGENT_CONFIG_TARGET="${PATRONI_ROLE_AGENT_CONFIG_TARGET:-/usr/local/sbin/patroni_role_agent_config.py}"
ROLE_IDENTITY_SOURCE="${PATRONI_ROLE_IDENTITY_SOURCE:-}"
ROLE_IDENTITY_TARGET="${PATRONI_ROLE_IDENTITY_TARGET:-/usr/local/sbin/patroni_local_identity.py}"
ROLE_UNIT_SOURCE="${PATRONI_ROLE_UNIT_SOURCE:-}"
ROLE_UNIT_TARGET="${PATRONI_ROLE_UNIT_TARGET:-/etc/systemd/system/mvn-patroni-role-agent.service}"
DB_CONTRACT_HELPER="${PATRONI_DB_CONTRACT_HELPER:-/tmp/patroni_compose_db_contract.py}"
ROLE_AGENT_UNIT="${PATRONI_ROLE_AGENT_UNIT:-mvn-patroni-role-agent.service}"
RECONCILE_SCRIPT="${API_RECONCILE_SCRIPT:-/tmp/reconcile_backend_compose_runtime.sh}"
COMMUNICATIONS_WORKER_RELEASE_HELPER="${COMMUNICATIONS_WORKER_RELEASE_HELPER:-${SCRIPT_DIR}/communications_worker_release_contract.sh}"
PATRONI_COMMUNICATIONS_CANDIDATE_LIFECYCLE="${PATRONI_COMMUNICATIONS_CANDIDATE_LIFECYCLE:-${SCRIPT_DIR}/patroni_communications_candidate_lifecycle.sh}"
PATRONI_ROLE_AGENT_CANDIDATE_ASSETS="${PATRONI_ROLE_AGENT_CANDIDATE_ASSETS:-${SCRIPT_DIR}/patroni_role_agent_candidate_assets.sh}"
DEPLOY_LOCK_FILE="${API_DEPLOY_LOCK_FILE:-${PROJECT_DIR}/.deploy.lock}"
DEPLOY_LOCK_FD="${API_DEPLOY_LOCK_FD:-}"
DEPLOY_LOCK_HELPER="${API_DEPLOY_LOCK_HELPER:-${SCRIPT_DIR}/safe_deploy_lock.py}"
DEPLOY_LOCK_HELPER_SHA256="${API_DEPLOY_LOCK_HELPER_SHA256:-}"
PATRONI_CUTOVER_MARKER="${PATRONI_CUTOVER_MARKER:-${PROJECT_DIR}/.patroni-cutover-in-progress}"
PITR_MAINTENANCE_MARKER="${API_PITR_MAINTENANCE_MARKER:-/run/mvn-postgres-pitr-maintenance}"
ACTIVE_SLOT_FILE="${API_ACTIVE_SLOT_FILE:-${PROJECT_DIR}/.active-api-slot}"
PREVIOUS_BACKEND_IMAGE="${API_PREVIOUS_BACKEND_IMAGE:-}"
BACKEND_IMAGE="${BACKEND_IMAGE:-}"
CANDIDATE_CHECKSUM=""
CANDIDATE_OWNED=false
PATRONI_URL="${API_PATRONI_URL:-http://127.0.0.1:8008/patroni}"
CURRENT_ROLE_OVERRIDE="${API_CURRENT_PATRONI_ROLE:-}"
EXPECTED_ROLE="${API_EXPECTED_PATRONI_ROLE:-}"
PROXY_MODE="${API_PROXY_MODE:-host_nginx}"
PROXY_CONFIG_SOURCE="${PATRONI_PROXY_CONFIG_SOURCE:-}"
PROXY_CONFIG_TARGET="${API_PROXY_CONFIG_FILE:-${PROJECT_DIR}/api-proxy/nginx.conf}"
PROXY_UPSTREAM_SOURCE="${PATRONI_PROXY_UPSTREAM_SOURCE:-}"
PROXY_UPSTREAM_TARGET="${API_NGINX_UPSTREAM_FILE:-${PROJECT_DIR}/api-proxy/upstream.conf}"
PROXY_SERVICE="${API_PROXY_SERVICE:-api-proxy}"
PROXY_CONFIG_BACKUP=""
PROXY_CONFIG_PREEXISTED=false
PROXY_UPSTREAM_CREATED=false
PROXY_FILES_CHANGED=false
PROXY_DIR_CREATED=false
PROXY_RUNTIME_STATE=not-applicable

[[ -f "${COMMUNICATIONS_WORKER_RELEASE_HELPER}" \
  && ! -L "${COMMUNICATIONS_WORKER_RELEASE_HELPER}" ]] \
  || { echo "communications worker release helper is missing or unsafe" >&2; exit 1; }
[[ -f "${PATRONI_COMMUNICATIONS_CANDIDATE_LIFECYCLE}" \
  && ! -L "${PATRONI_COMMUNICATIONS_CANDIDATE_LIFECYCLE}" ]] \
  || { echo "Patroni communications candidate lifecycle is missing or unsafe" >&2; exit 1; }
[[ -f "${PATRONI_ROLE_AGENT_CANDIDATE_ASSETS}" \
  && ! -L "${PATRONI_ROLE_AGENT_CANDIDATE_ASSETS}" ]] \
  || { echo "Patroni role-agent candidate assets helper is missing or unsafe" >&2; exit 1; }
# shellcheck disable=SC1090
source "${COMMUNICATIONS_WORKER_RELEASE_HELPER}"
# shellcheck disable=SC1090
source "${PATRONI_COMMUNICATIONS_CANDIDATE_LIFECYCLE}"
# shellcheck disable=SC1090
source "${PATRONI_ROLE_AGENT_CANDIDATE_ASSETS}"

[[ "${DEPLOY_LOCK_HELPER_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
  echo "safe deployment lock helper digest is missing" >&2; exit 1;
}
python3 - "${DEPLOY_LOCK_HELPER}" "${DEPLOY_LOCK_HELPER_SHA256}" <<'PY'
import hashlib, os, stat, sys
path, expected = sys.argv[1:]
before = os.lstat(path)
if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
        or before.st_uid != os.geteuid() or before.st_nlink != 1
        or before.st_mode & 0o022):
    raise SystemExit("safe deployment lock helper metadata is unsafe")
fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
try:
    opened = os.fstat(fd); data = b""
    while True:
        chunk = os.read(fd, 131072)
        if not chunk: break
        data += chunk
finally: os.close(fd)
if ((opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        or hashlib.sha256(data).hexdigest() != expected):
    raise SystemExit("safe deployment lock helper source is unreviewed")
PY
if [[ -z "${DEPLOY_LOCK_FD}" ]]; then
  exec python3 "${DEPLOY_LOCK_HELPER}" exec "${DEPLOY_LOCK_FILE}" bash "$0" "$@"
fi
[[ "${DEPLOY_LOCK_FD}" == "9" ]] || {
  echo "candidate transaction requires inherited deployment lock fd 9" >&2
  exit 1
}
python3 "${DEPLOY_LOCK_HELPER}" verify "${DEPLOY_LOCK_FILE}" "${DEPLOY_LOCK_FD}"

require_no_patroni_cutover() {
  if [[ -e "${PATRONI_CUTOVER_MARKER}" || -L "${PATRONI_CUTOVER_MARKER}" ]]; then
    echo "Patroni database rollout is in progress: ${PATRONI_CUTOVER_MARKER}" >&2
    return 1
  fi
}

require_no_pitr_maintenance() {
  if [[ -e "${PITR_MAINTENANCE_MARKER}" || -L "${PITR_MAINTENANCE_MARKER}" ]]; then
    echo "PITR release maintenance is active: ${PITR_MAINTENANCE_MARKER}" >&2
    return 1
  fi
}

transaction() {
  CANONICAL_COMPOSE_FILE="${CANONICAL_FILE}" \
    CANDIDATE_COMPOSE_FILE="${CANDIDATE_FILE}" \
    bash "${TRANSACTION_SCRIPT}" "$1"
}

stage_candidate_compose() {
  local temporary=""
  [[ "$(dirname "${CANONICAL_FILE}")" == "$(dirname "${CANDIDATE_FILE}")" ]] || {
    echo "candidate and canonical compose must share a directory" >&2
    return 1
  }
  if [[ -z "${CANDIDATE_SOURCE}" ]]; then
    [[ -f "${CANDIDATE_FILE}" && ! -L "${CANDIDATE_FILE}" ]] || {
      echo "candidate compose is missing or unsafe: ${CANDIDATE_FILE}" >&2
      return 1
    }
    CANDIDATE_OWNED=true
    trap cleanup_candidate_only EXIT
    return 0
  fi
  [[ -f "${CANDIDATE_SOURCE}" && ! -L "${CANDIDATE_SOURCE}" ]] || {
    echo "candidate compose source is missing or unsafe: ${CANDIDATE_SOURCE}" >&2
    return 1
  }
  [[ ! -e "${CANDIDATE_FILE}" && ! -L "${CANDIDATE_FILE}" ]] || {
    echo "candidate compose target already exists: ${CANDIDATE_FILE}" >&2
    return 1
  }
  CANDIDATE_OWNED=true
  trap cleanup_candidate_only EXIT
  temporary="$(mktemp "${CANDIDATE_FILE}.tmp.XXXXXX")"
  if ! cp -p -- "${CANDIDATE_SOURCE}" "${temporary}"; then
    rm -f -- "${temporary}"
    return 1
  fi
  if ! mv -- "${temporary}" "${CANDIDATE_FILE}"; then
    rm -f -- "${temporary}"
    return 1
  fi
}
cleanup_migration_candidate() {
  local status=$?
  trap - EXIT
  set +e
  [[ "${CANDIDATE_OWNED}" == "true" ]] && transaction cleanup
  exit "${status}"
}
cleanup_candidate_only() {
  local status=$?
  trap - EXIT
  set +e
  [[ "${CANDIDATE_OWNED}" == "true" ]] && transaction cleanup
  exit "${status}"
}
resolve_previous_backend_image() {
  local active_service="app"
  local active_slot=""
  local container_ids=""
  local runtime_image=""
  if [[ -n "${PREVIOUS_BACKEND_IMAGE}" ]]; then
    [[ "${PREVIOUS_BACKEND_IMAGE}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]] || {
      echo "API_PREVIOUS_BACKEND_IMAGE must be immutable" >&2
      return 1
    }
    return 0
  fi
  if [[ -f "${ACTIVE_SLOT_FILE}" ]]; then
    active_slot="$(tr -d '\r\n' < "${ACTIVE_SLOT_FILE}")"
    case "${active_slot}" in
      blue|green) active_service="app-${active_slot}" ;;
      *) echo "invalid active API slot: ${active_slot}" >&2; return 1 ;;
    esac
  fi
  container_ids="$(docker compose -f "${CANONICAL_FILE}" --profile bluegreen ps -q "${active_service}")"
  [[ -n "${container_ids}" && "${container_ids}" != *$'\n'* ]] || {
    echo "could not resolve exactly one active Patroni API container" >&2
    return 1
  }
  runtime_image="$(docker inspect --format '{{.Config.Image}}' "${container_ids}")"
  [[ "${runtime_image}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]] || {
    echo "active Patroni API runtime image is not immutable" >&2
    return 1
  }
  PREVIOUS_BACKEND_IMAGE="${runtime_image}"
}

atomic_install_file() {
  local source="$1"
  local target="$2"
  local mode="${3:-0644}"
  local temporary=""
  temporary="$(mktemp "${target}.tmp.XXXXXX")"
  if ! install -m "${mode}" -- "${source}" "${temporary}"; then
    rm -f -- "${temporary}"
    return 1
  fi
  mv -f -- "${temporary}" "${target}"
}
atomic_restore_file() {
  local source="$1"
  local target="$2"
  local temporary=""
  temporary="$(mktemp "${target}.tmp.XXXXXX")"
  if ! cp -p -- "${source}" "${temporary}"; then
    rm -f -- "${temporary}"
    return 1
  fi
  mv -f -- "${temporary}" "${target}"
}
require_safe_proxy_target() {
  python3 - "$1" <<'PY'
import os, stat, sys
metadata = os.lstat(sys.argv[1])
if (not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid() or metadata.st_nlink != 1
        or metadata.st_mode & 0o022):
    raise SystemExit("container proxy target metadata is unsafe: " + sys.argv[1])
PY
}
capture_proxy_runtime_state() {
  local container_ids=""
  local running=""
  [[ "${PROXY_MODE}" == "container_nginx" ]] || return 0
  container_ids="$(docker compose -f "${CANONICAL_FILE}" --profile bluegreen \
    ps -a -q "${PROXY_SERVICE}")"
  if [[ -z "${container_ids}" ]]; then
    PROXY_RUNTIME_STATE=absent
    return 0
  fi
  [[ "${container_ids}" != *$'\n'* ]] || {
    echo "container proxy runtime is ambiguous" >&2
    return 1
  }
  running="$(docker inspect --format '{{.State.Running}}' "${container_ids}")"
  case "${running}" in
    true) PROXY_RUNTIME_STATE=running ;;
    false) PROXY_RUNTIME_STATE=stopped ;;
    *) echo "container proxy runtime state is invalid" >&2; return 1 ;;
  esac
}
stage_proxy_files() {
  local proxy_dir=""
  [[ "${PROXY_MODE}" == "container_nginx" ]] || return 0
  [[ -f "${PROXY_CONFIG_SOURCE}" && ! -L "${PROXY_CONFIG_SOURCE}" \
    && -f "${PROXY_UPSTREAM_SOURCE}" && ! -L "${PROXY_UPSTREAM_SOURCE}" ]] || {
    echo "container proxy source bundle is incomplete" >&2
    return 1
  }
  proxy_dir="$(dirname "${PROXY_CONFIG_TARGET}")"
  [[ "${proxy_dir}" == "$(dirname "${PROXY_UPSTREAM_TARGET}")" ]] || {
    echo "container proxy targets must share one directory" >&2
    return 1
  }
  if [[ -e "${proxy_dir}" || -L "${proxy_dir}" ]]; then
    [[ -d "${proxy_dir}" && ! -L "${proxy_dir}" ]] || {
      echo "container proxy directory is unsafe: ${proxy_dir}" >&2
      return 1
    }
  else
    mkdir -m 0755 -- "${proxy_dir}"
    PROXY_DIR_CREATED=true
  fi
  if [[ -e "${PROXY_CONFIG_TARGET}" || -L "${PROXY_CONFIG_TARGET}" ]]; then
    [[ -f "${PROXY_CONFIG_TARGET}" && ! -L "${PROXY_CONFIG_TARGET}" ]] || {
      echo "container proxy config target is unsafe" >&2
      return 1
    }
    require_safe_proxy_target "${PROXY_CONFIG_TARGET}"
    PROXY_CONFIG_BACKUP="$(mktemp "${PROJECT_DIR}/.patroni-proxy-config.backup.XXXXXX")"
    if ! cp -p -- "${PROXY_CONFIG_TARGET}" "${PROXY_CONFIG_BACKUP}"; then
      rm -f -- "${PROXY_CONFIG_BACKUP}"
      PROXY_CONFIG_BACKUP=""
      return 1
    fi
    PROXY_CONFIG_PREEXISTED=true
  fi
  if [[ -e "${PROXY_UPSTREAM_TARGET}" || -L "${PROXY_UPSTREAM_TARGET}" ]]; then
    [[ -f "${PROXY_UPSTREAM_TARGET}" && ! -L "${PROXY_UPSTREAM_TARGET}" ]] || {
      echo "container proxy upstream target is unsafe" >&2
      return 1
    }
    require_safe_proxy_target "${PROXY_UPSTREAM_TARGET}"
  fi
  PROXY_FILES_CHANGED=true
  atomic_install_file "${PROXY_CONFIG_SOURCE}" "${PROXY_CONFIG_TARGET}"
  if [[ ! -e "${PROXY_UPSTREAM_TARGET}" ]]; then
    atomic_install_file "${PROXY_UPSTREAM_SOURCE}" "${PROXY_UPSTREAM_TARGET}"
    PROXY_UPSTREAM_CREATED=true
  fi
}

restore_proxy_files() {
  [[ "${PROXY_FILES_CHANGED}" == "true" || "${PROXY_DIR_CREATED}" == "true" ]] || return 0
  local failed=false
  if [[ "${PROXY_FILES_CHANGED}" == "true" ]]; then
    if [[ "${PROXY_CONFIG_PREEXISTED}" == "true" ]]; then
      atomic_restore_file "${PROXY_CONFIG_BACKUP}" "${PROXY_CONFIG_TARGET}" || failed=true
    else
      rm -f -- "${PROXY_CONFIG_TARGET}" || failed=true
    fi
    if [[ "${PROXY_UPSTREAM_CREATED}" == "true" ]]; then
      rm -f -- "${PROXY_UPSTREAM_TARGET}" || failed=true
    fi
  fi
  [[ -z "${PROXY_CONFIG_BACKUP}" ]] || rm -f -- "${PROXY_CONFIG_BACKUP}" || failed=true
  if [[ "${PROXY_DIR_CREATED}" == "true" ]]; then
    rmdir -- "$(dirname "${PROXY_CONFIG_TARGET}")" || failed=true
  fi
  [[ "${failed}" == "false" ]]
}

restore_proxy_runtime() {
  [[ "${PROXY_MODE}" == "container_nginx" \
    && "${PROXY_FILES_CHANGED}" == "true" ]] || return 0
  case "${PROXY_RUNTIME_STATE}" in
    absent)
      docker compose -f "${CANONICAL_FILE}" --profile bluegreen \
        rm -s -f "${PROXY_SERVICE}" >/dev/null \
        && [[ -z "$(docker compose -f "${CANONICAL_FILE}" --profile bluegreen \
          ps -a -q "${PROXY_SERVICE}")" ]]
      ;;
    stopped)
      docker compose -f "${CANONICAL_FILE}" --profile bluegreen \
        stop "${PROXY_SERVICE}" >/dev/null \
        && [[ -z "$(docker compose -f "${CANONICAL_FILE}" --profile bluegreen \
          ps --status running -q "${PROXY_SERVICE}")" ]]
      ;;
    running)
      docker compose -f "${CANONICAL_FILE}" --profile bluegreen \
        up -d --no-deps --force-recreate --wait --wait-timeout 60 "${PROXY_SERVICE}" \
        && docker compose -f "${CANONICAL_FILE}" --profile bluegreen \
          exec -T "${PROXY_SERVICE}" nginx -t
      ;;
    *) echo "container proxy pre-deploy runtime state is unavailable" >&2; return 1 ;;
  esac
}

restore_proxy_state() {
  local failed=false
  if [[ "${PROXY_RUNTIME_STATE}" == "absent" \
    || "${PROXY_RUNTIME_STATE}" == "stopped" ]]; then
    restore_proxy_runtime || failed=true
    restore_proxy_files || failed=true
  else
    restore_proxy_files || failed=true
    restore_proxy_runtime || failed=true
  fi
  [[ "${failed}" == "false" ]]
}

current_patroni_role() {
  if [[ -n "${CURRENT_ROLE_OVERRIDE}" ]]; then
    [[ "${CURRENT_ROLE_OVERRIDE}" == "primary" || "${CURRENT_ROLE_OVERRIDE}" == "standby" ]] \
      || return 1
    printf '%s\n' "${CURRENT_ROLE_OVERRIDE}"
    return 0
  fi
  curl -fsS --max-time 5 "${PATRONI_URL}" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
if payload.get("state") != "running":
    raise SystemExit(1)
role = str(payload.get("role") or "").lower()
if role in {"leader", "master", "primary"}:
    print("primary")
elif role in {"replica", "standby"}:
    print("standby")
else:
    raise SystemExit(1)
'
}

db_contract_digest() {
  local compose_file="$1"
  local rendered=""

  rendered="$(
    docker compose -f "${compose_file}" config \
      --no-env-resolution --no-interpolate --format json \
      | python3 "${DB_CONTRACT_HELPER}"
  )" || {
    echo "could not render the complete Patroni db contract" >&2
    return 1
  }
  [[ "${rendered}" =~ ^[0-9a-f]{64}$ ]] || {
    echo "invalid Patroni db contract digest" >&2
    return 1
  }
  printf '%s\n' "${rendered}"
}

require_unchanged_db_contract() {
  local canonical_hash=""
  local candidate_hash=""

  canonical_hash="$(db_contract_digest "${CANONICAL_FILE}")"
  candidate_hash="$(db_contract_digest "${CANDIDATE_FILE}")"
  [[ "${canonical_hash}" == "${candidate_hash}" ]] || {
    echo "candidate changes the Patroni db contract; use the reviewed database rollout controller" >&2
    return 1
  }
}

fence_runtime_for_role_drift() {
  local services=(app app-blue app-green bot)
  local failed=false
  communications_worker_set_release_fence || failed=true
  docker compose -f "${CANONICAL_FILE}" --profile bluegreen \
    stop "${services[@]}" >/dev/null 2>&1 || failed=true
  patroni_communications_force_fence_candidate_runtime || failed=true
  [[ "${failed}" == "false" ]]
}

reconcile_failed_deploy() {
  local status=$?
  local restoration_failed=false
  local role_agent_restore_failed=false
  local recovery_role=""
  local recovery_services="app"
  trap - EXIT
  set +e
  if promotion_committed; then
    if ! patroni_communications_fence_canonical; then
      echo "CRITICAL: promoted communications worker could not be fenced" >&2
      exit 90
    fi
    echo "Patroni candidate compose promotion committed; fenced the dormant worker for inspection" >&2
    patroni_role_assets_cleanup_backups \
      || echo "warning: stale Patroni role asset backup remains" >&2
    [[ -z "${PROXY_CONFIG_BACKUP}" ]] || rm -f -- "${PROXY_CONFIG_BACKUP}"
    exit "${status}"
  fi
  if ! patroni_communications_fence_candidate; then
    echo "failed to fence candidate communications worker before rollback" >&2
    restoration_failed=true
  fi
  transaction cleanup || restoration_failed=true
  if ! restore_proxy_state; then
    echo "failed to restore the previous container proxy files and runtime state" >&2
    restoration_failed=true
  fi
  if ! patroni_role_assets_restore; then
    echo "failed to restore the previous Patroni role agent" >&2
    role_agent_restore_failed=true
    restoration_failed=true
  fi
  if ! recovery_role="$(current_patroni_role)"; then
    echo "CRITICAL: could not establish live Patroni role during recovery; fencing API and bot" >&2
    fence_runtime_for_role_drift || restoration_failed=true
    restoration_failed=true
  elif [[ "${recovery_role}" != "${EXPECTED_ROLE}" ]]; then
    echo "CRITICAL: Patroni role changed during deployment (expected=${EXPECTED_ROLE}, live=${recovery_role}); fencing API and bot until the role agent reconciles fresh role state" >&2
    fence_runtime_for_role_drift || restoration_failed=true
    restoration_failed=true
  elif [[ "${recovery_role}" == "primary" ]]; then
    if [[ "${PREVIOUS_WORKER_RUNNING}" == "true" ]]; then
      recovery_services+=" ${COMMUNICATIONS_WORKER_SERVICE}"
    fi
    if ! API_DEPLOY_SERVICES="${recovery_services}" \
      API_COMPOSE_FILE="$(basename "${CANONICAL_FILE}")" \
      API_RECONCILE_BACKEND_IMAGE="${PREVIOUS_BACKEND_IMAGE}" \
      API_READY_URL="${API_HEALTH_URL:-http://127.0.0.1:18080/api/health}" \
      bash "${RECONCILE_SCRIPT}"; then
      restoration_failed=true
    fi
  else
    recovery_services="app"
    if [[ "${PREVIOUS_WORKER_RUNNING}" == "true" ]]; then
      recovery_services+=" ${COMMUNICATIONS_WORKER_SERVICE}"
    fi
    if ! API_DEPLOY_SERVICES="${recovery_services}" \
      API_STOP_SERVICES_AFTER_DEPLOY="bot" \
      API_COMPOSE_FILE="$(basename "${CANONICAL_FILE}")" \
      API_RECONCILE_BACKEND_IMAGE="${PREVIOUS_BACKEND_IMAGE}" \
      API_READY_URL="${API_HEALTH_URL:-http://127.0.0.1:18080/api/health}" \
      bash "${RECONCILE_SCRIPT}"; then
      restoration_failed=true
    fi
  fi
  patroni_role_assets_cleanup_sources || restoration_failed=true
  if [[ "${restoration_failed}" == "true" ]]; then
    communications_worker_set_release_fence || true
  elif ! patroni_communications_restore_release_fence; then
    echo "failed to restore the previous communications worker release fence" >&2
    communications_worker_set_release_fence || true
    restoration_failed=true
  fi
  if ! patroni_communications_require_previous_fence_restored; then
    echo "failed to prove the previous communications worker fence" >&2
    communications_worker_set_release_fence || true
    restoration_failed=true
  fi
  if patroni_role_assets_backups_present; then
    if [[ "${role_agent_restore_failed}" == "true" ]]; then
      echo "CRITICAL: previous Patroni role asset backups retained" >&2
    else
      patroni_role_assets_cleanup_backups || restoration_failed=true
    fi
  fi
  if [[ "${restoration_failed}" == "true" ]]; then
    echo "CRITICAL: failed Patroni candidate could not be fully restored" >&2
    exit 90
  fi
  exit "${status}"
}

promotion_committed() {
  local canonical_checksum=""
  [[ -n "${CANDIDATE_CHECKSUM}" && ! -e "${CANDIDATE_FILE}" ]] || return 1
  [[ -f "${CANONICAL_FILE}" && ! -L "${CANONICAL_FILE}" ]] || return 1
  canonical_checksum="$(cksum < "${CANONICAL_FILE}")" || return 1
  [[ "${canonical_checksum}" == "${CANDIDATE_CHECKSUM}" ]]
}

[[ "${OPERATION}" == "migrate" || "${OPERATION}" == "deploy" ]] || {
  echo "PATRONI_CANDIDATE_OPERATION must be migrate or deploy" >&2
  exit 2
}
if [[ "${OPERATION}" == "deploy" ]]; then
  [[ "${EXPECTED_ROLE}" == "primary" || "${EXPECTED_ROLE}" == "standby" ]] || {
    echo "API_EXPECTED_PATRONI_ROLE must be primary or standby" >&2
    exit 2
  }
  [[ "${BACKEND_IMAGE}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]] || {
    echo "BACKEND_IMAGE must identify an immutable candidate release" >&2
    exit 2
  }
fi
[[ -n "${CANDIDATE_FILE}" ]] || {
  echo "PATRONI_CANDIDATE_COMPOSE_FILE must name this run's unique candidate" >&2
  exit 1
}
[[ -f "${TRANSACTION_SCRIPT}" ]] || {
  echo "compose transaction helper is missing: ${TRANSACTION_SCRIPT}" >&2
  exit 1
}
require_no_pitr_maintenance
require_no_patroni_cutover
stage_candidate_compose
CANDIDATE_CHECKSUM="$(cksum < "${CANDIDATE_FILE}")"
trap cleanup_candidate_only EXIT
if [[ "${OPERATION}" == "migrate" ]]; then
  trap cleanup_migration_candidate EXIT
  API_DEPLOY_LOCK_FD="${DEPLOY_LOCK_FD}" \
    API_COMPOSE_FILE="$(basename "${CANDIDATE_FILE}")" bash "${MIGRATION_SCRIPT}"
  trap - EXIT
  transaction cleanup
  exit 0
fi

[[ -f "${DB_CONTRACT_HELPER}" && ! -L "${DB_CONTRACT_HELPER}" ]] || {
  echo "Patroni db contract helper is missing or unsafe: ${DB_CONTRACT_HELPER}" >&2
  exit 1
}
require_unchanged_db_contract
resolve_previous_backend_image
patroni_communications_capture_release_fence
patroni_communications_capture_previous
patroni_role_assets_backup
trap reconcile_failed_deploy EXIT
transaction stage
patroni_communications_detect_candidate_support

patroni_role_assets_install
capture_proxy_runtime_state
stage_proxy_files

API_COMPOSE_FILE="$(basename "${CANDIDATE_FILE}")" \
  API_DEPLOY_LOCK_FD="${DEPLOY_LOCK_FD}" \
bash "${DEPLOY_SCRIPT}"
require_no_patroni_cutover
require_unchanged_db_contract
if [[ "${CANDIDATE_WORKER_SUPPORTED}" == "true" ]]; then
  patroni_communications_require_runtime "${CANDIDATE_FILE}" "${BACKEND_IMAGE}"
fi
transaction promote
if [[ "${CANDIDATE_WORKER_SUPPORTED}" == "true" ]]; then
  patroni_communications_require_runtime "${CANONICAL_FILE}" "${BACKEND_IMAGE}"
fi
trap - EXIT
patroni_role_assets_cleanup_backups \
  || echo "warning: stale Patroni role asset backup remains" >&2
[[ -z "${PROXY_CONFIG_BACKUP}" ]] || rm -f -- "${PROXY_CONFIG_BACKUP}" \
  || echo "warning: stale Patroni proxy config backup remains at ${PROXY_CONFIG_BACKUP}" >&2
