#!/usr/bin/env bash
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
ROLE_IDENTITY_SOURCE="${PATRONI_ROLE_IDENTITY_SOURCE:-}"
ROLE_IDENTITY_TARGET="${PATRONI_ROLE_IDENTITY_TARGET:-/usr/local/sbin/patroni_local_identity.py}"
DB_CONTRACT_HELPER="${PATRONI_DB_CONTRACT_HELPER:-/tmp/patroni_compose_db_contract.py}"
ROLE_AGENT_UNIT="${PATRONI_ROLE_AGENT_UNIT:-mvn-patroni-role-agent.service}"
RECONCILE_SCRIPT="${API_RECONCILE_SCRIPT:-/tmp/reconcile_backend_compose_runtime.sh}"
DEPLOY_LOCK_FILE="${API_DEPLOY_LOCK_FILE:-${PROJECT_DIR}/.deploy.lock}"
DEPLOY_LOCK_FD="${API_DEPLOY_LOCK_FD:-}"
DEPLOY_LOCK_HELPER="${API_DEPLOY_LOCK_HELPER:-${SCRIPT_DIR}/safe_deploy_lock.py}"
DEPLOY_LOCK_HELPER_SHA256="${API_DEPLOY_LOCK_HELPER_SHA256:-}"
PATRONI_CUTOVER_MARKER="${PATRONI_CUTOVER_MARKER:-${PROJECT_DIR}/.patroni-cutover-in-progress}"
PITR_MAINTENANCE_MARKER="${API_PITR_MAINTENANCE_MARKER:-/run/mvn-postgres-pitr-maintenance}"
ACTIVE_SLOT_FILE="${API_ACTIVE_SLOT_FILE:-${PROJECT_DIR}/.active-api-slot}"
PREVIOUS_BACKEND_IMAGE="${API_PREVIOUS_BACKEND_IMAGE:-}"
ROLE_AGENT_BACKUP=""
ROLE_AGENT_PREEXISTED=false
ROLE_IDENTITY_BACKUP=""
ROLE_IDENTITY_PREEXISTED=false
ROLE_AGENT_CHANGED=false
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

backup_role_agent() {
  if [[ -e "${ROLE_AGENT_TARGET}" || -L "${ROLE_AGENT_TARGET}" ]]; then
    [[ -f "${ROLE_AGENT_TARGET}" && ! -L "${ROLE_AGENT_TARGET}" ]] || {
      echo "existing Patroni role agent target is unsafe" >&2
      return 1
    }
  fi
  if [[ -e "${ROLE_IDENTITY_TARGET}" || -L "${ROLE_IDENTITY_TARGET}" ]]; then
    [[ -f "${ROLE_IDENTITY_TARGET}" && ! -L "${ROLE_IDENTITY_TARGET}" ]] || {
      echo "existing Patroni identity helper target is unsafe" >&2
      return 1
    }
  fi
  if [[ -f "${ROLE_AGENT_TARGET}" ]]; then
    systemctl is-active --quiet "${ROLE_AGENT_UNIT}" || {
      echo "existing Patroni role agent unit is not active" >&2
      return 1
    }
    ROLE_AGENT_BACKUP="$(mktemp "${PROJECT_DIR}/.patroni-role-agent.backup.XXXXXX")"
    if ! cp -p -- "${ROLE_AGENT_TARGET}" "${ROLE_AGENT_BACKUP}"; then
      rm -f -- "${ROLE_AGENT_BACKUP}"
      ROLE_AGENT_BACKUP=""
      return 1
    fi
    ROLE_AGENT_PREEXISTED=true
  fi
  if [[ -f "${ROLE_IDENTITY_TARGET}" ]]; then
    ROLE_IDENTITY_BACKUP="$(mktemp "${PROJECT_DIR}/.patroni-role-identity.backup.XXXXXX")"
    if ! cp -p -- "${ROLE_IDENTITY_TARGET}" "${ROLE_IDENTITY_BACKUP}"; then
      rm -f -- "${ROLE_AGENT_BACKUP}" "${ROLE_IDENTITY_BACKUP}"
      ROLE_AGENT_BACKUP=""
      ROLE_AGENT_PREEXISTED=false
      ROLE_IDENTITY_BACKUP=""
      return 1
    fi
    ROLE_IDENTITY_PREEXISTED=true
  fi
}

restore_role_agent() {
  [[ "${ROLE_AGENT_CHANGED}" == "true" ]] || return 0
  local failed=false
  if [[ "${ROLE_IDENTITY_PREEXISTED}" == "true" ]]; then
    cp -p -- "${ROLE_IDENTITY_BACKUP}" "${ROLE_IDENTITY_TARGET}" || failed=true
  else
    rm -f -- "${ROLE_IDENTITY_TARGET}" || failed=true
  fi
  if [[ "${ROLE_AGENT_PREEXISTED}" == "true" ]]; then
    cp -p -- "${ROLE_AGENT_BACKUP}" "${ROLE_AGENT_TARGET}" || failed=true
    systemctl restart "${ROLE_AGENT_UNIT}" || failed=true
    systemctl is-active --quiet "${ROLE_AGENT_UNIT}" || failed=true
  else
    systemctl stop "${ROLE_AGENT_UNIT}" >/dev/null 2>&1 || failed=true
    if systemctl is-active --quiet "${ROLE_AGENT_UNIT}"; then
      echo "new Patroni role agent unit remained active after stop" >&2
      failed=true
    fi
    rm -f -- "${ROLE_AGENT_TARGET}" || failed=true
  fi
  [[ "${failed}" == "false" ]]
}

atomic_install_file() {
  local source="$1"
  local target="$2"
  local temporary=""
  temporary="$(mktemp "${target}.tmp.XXXXXX")"
  if ! install -m 0644 -- "${source}" "${temporary}"; then
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
  docker compose -f "${CANONICAL_FILE}" --profile bluegreen \
    stop app app-blue app-green bot >/dev/null 2>&1
}

reconcile_failed_deploy() {
  local status=$?
  local restoration_failed=false
  local role_agent_restore_failed=false
  local recovery_role=""
  trap - EXIT
  set +e
  if promotion_committed; then
    echo "Patroni candidate compose promotion committed; preserving the consistent new runtime" >&2
    [[ -z "${ROLE_AGENT_BACKUP}" ]] || rm -f -- "${ROLE_AGENT_BACKUP}"
    [[ -z "${ROLE_IDENTITY_BACKUP}" ]] || rm -f -- "${ROLE_IDENTITY_BACKUP}"
    [[ -z "${PROXY_CONFIG_BACKUP}" ]] || rm -f -- "${PROXY_CONFIG_BACKUP}"
    exit "${status}"
  fi
  transaction cleanup || restoration_failed=true
  if ! restore_proxy_state; then
    echo "failed to restore the previous container proxy files and runtime state" >&2
    restoration_failed=true
  fi
  if ! restore_role_agent; then
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
    if ! API_DEPLOY_SERVICES="app bot" \
      API_COMPOSE_FILE="$(basename "${CANONICAL_FILE}")" \
      API_RECONCILE_BACKEND_IMAGE="${PREVIOUS_BACKEND_IMAGE}" \
      API_READY_URL="${API_HEALTH_URL:-http://127.0.0.1:18080/api/health}" \
      bash "${RECONCILE_SCRIPT}"; then
      restoration_failed=true
    fi
  else
    if ! API_DEPLOY_SERVICES="app" \
      API_STOP_SERVICES_AFTER_DEPLOY="bot" \
      API_COMPOSE_FILE="$(basename "${CANONICAL_FILE}")" \
      API_RECONCILE_BACKEND_IMAGE="${PREVIOUS_BACKEND_IMAGE}" \
      API_READY_URL="${API_HEALTH_URL:-http://127.0.0.1:18080/api/health}" \
      bash "${RECONCILE_SCRIPT}"; then
      restoration_failed=true
    fi
  fi
  [[ -z "${ROLE_AGENT_SOURCE}" ]] || rm -f -- "${ROLE_AGENT_SOURCE}"
  [[ -z "${ROLE_IDENTITY_SOURCE}" ]] || rm -f -- "${ROLE_IDENTITY_SOURCE}"
  if [[ -n "${ROLE_AGENT_BACKUP}" || -n "${ROLE_IDENTITY_BACKUP}" ]]; then
    if [[ "${role_agent_restore_failed}" == "true" ]]; then
      echo "CRITICAL: previous Patroni role asset backups retained" >&2
    else
      [[ -z "${ROLE_AGENT_BACKUP}" ]] \
        || rm -f -- "${ROLE_AGENT_BACKUP}" || restoration_failed=true
      [[ -z "${ROLE_IDENTITY_BACKUP}" ]] \
        || rm -f -- "${ROLE_IDENTITY_BACKUP}" || restoration_failed=true
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
backup_role_agent
trap reconcile_failed_deploy EXIT
transaction stage

[[ -f "${ROLE_AGENT_SOURCE}" && ! -L "${ROLE_AGENT_SOURCE}" \
  && -f "${ROLE_IDENTITY_SOURCE}" && ! -L "${ROLE_IDENTITY_SOURCE}" ]] || {
  echo "Patroni role agent source bundle is incomplete" >&2
  exit 1
}
ROLE_AGENT_CHANGED=true
install -m 0644 "${ROLE_IDENTITY_SOURCE}" "${ROLE_IDENTITY_TARGET}"
install -m 0755 "${ROLE_AGENT_SOURCE}" "${ROLE_AGENT_TARGET}"
rm -f -- "${ROLE_AGENT_SOURCE}" "${ROLE_IDENTITY_SOURCE}"
systemctl restart "${ROLE_AGENT_UNIT}"
systemctl is-active --quiet "${ROLE_AGENT_UNIT}"
capture_proxy_runtime_state
stage_proxy_files

API_COMPOSE_FILE="$(basename "${CANDIDATE_FILE}")" \
  API_DEPLOY_LOCK_FD="${DEPLOY_LOCK_FD}" \
bash "${DEPLOY_SCRIPT}"
require_no_patroni_cutover
require_unchanged_db_contract
transaction promote
trap - EXIT
[[ -z "${ROLE_AGENT_BACKUP}" ]] || rm -f -- "${ROLE_AGENT_BACKUP}" \
  || echo "warning: stale Patroni role agent backup remains at ${ROLE_AGENT_BACKUP}" >&2
[[ -z "${ROLE_IDENTITY_BACKUP}" ]] || rm -f -- "${ROLE_IDENTITY_BACKUP}" \
  || echo "warning: stale Patroni identity backup remains at ${ROLE_IDENTITY_BACKUP}" >&2
[[ -z "${PROXY_CONFIG_BACKUP}" ]] || rm -f -- "${PROXY_CONFIG_BACKUP}" \
  || echo "warning: stale Patroni proxy config backup remains at ${PROXY_CONFIG_BACKUP}" >&2
