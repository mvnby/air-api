#!/usr/bin/env bash
set -Eeuo pipefail

OPERATION="${PATRONI_CANDIDATE_OPERATION:-}"
PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
CANONICAL_FILE="${PATRONI_CANONICAL_COMPOSE_FILE:-${PROJECT_DIR}/docker-compose.patroni.yml}"
CANDIDATE_FILE="${PATRONI_CANDIDATE_COMPOSE_FILE:-}"
TRANSACTION_SCRIPT="${COMPOSE_CANDIDATE_TRANSACTION_SCRIPT:-/tmp/compose_candidate_transaction.sh}"
MIGRATION_SCRIPT="${PATRONI_MIGRATION_SCRIPT:-/tmp/run_patroni_migrations.sh}"
DEPLOY_SCRIPT="${PATRONI_DEPLOY_SCRIPT:-/tmp/deploy_patroni_api_node.sh}"
ROLE_AGENT_SOURCE="${PATRONI_ROLE_AGENT_SOURCE:-}"
ROLE_AGENT_TARGET="${PATRONI_ROLE_AGENT_TARGET:-/usr/local/sbin/mvn-patroni-role-agent}"
ROLE_IDENTITY_SOURCE="${PATRONI_ROLE_IDENTITY_SOURCE:-}"
ROLE_IDENTITY_TARGET="${PATRONI_ROLE_IDENTITY_TARGET:-/usr/local/sbin/patroni_local_identity.py}"
ROLE_AGENT_UNIT="${PATRONI_ROLE_AGENT_UNIT:-mvn-patroni-role-agent.service}"
RECONCILE_SCRIPT="${API_RECONCILE_SCRIPT:-/tmp/reconcile_backend_compose_runtime.sh}"
DEPLOY_LOCK_FILE="${API_DEPLOY_LOCK_FILE:-${PROJECT_DIR}/.deploy.lock}"
ACTIVE_SLOT_FILE="${API_ACTIVE_SLOT_FILE:-${PROJECT_DIR}/.active-api-slot}"
PREVIOUS_BACKEND_IMAGE="${API_PREVIOUS_BACKEND_IMAGE:-}"
ROLE_AGENT_BACKUP=""
ROLE_AGENT_PREEXISTED=false
ROLE_IDENTITY_BACKUP=""
ROLE_IDENTITY_PREEXISTED=false
ROLE_AGENT_CHANGED=false
CANDIDATE_CHECKSUM=""
PATRONI_URL="${API_PATRONI_URL:-http://127.0.0.1:8008/patroni}"
CURRENT_ROLE_OVERRIDE="${API_CURRENT_PATRONI_ROLE:-}"
EXPECTED_ROLE="${API_EXPECTED_PATRONI_ROLE:-}"

transaction() {
  CANONICAL_COMPOSE_FILE="${CANONICAL_FILE}" \
    CANDIDATE_COMPOSE_FILE="${CANDIDATE_FILE}" \
    bash "${TRANSACTION_SCRIPT}" "$1"
}

cleanup_migration_candidate() {
  local status=$?
  trap - EXIT
  set +e
  transaction cleanup
  exit "${status}"
}

cleanup_candidate_only() {
  local status=$?
  trap - EXIT
  set +e
  transaction cleanup
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
    exit "${status}"
  fi
  transaction cleanup || restoration_failed=true
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
[[ -f "${CANDIDATE_FILE}" ]] || {
  echo "candidate compose is missing: ${CANDIDATE_FILE}" >&2
  exit 1
}
CANDIDATE_CHECKSUM="$(cksum < "${CANDIDATE_FILE}")"
[[ -f "${TRANSACTION_SCRIPT}" ]] || {
  echo "compose transaction helper is missing: ${TRANSACTION_SCRIPT}" >&2
  exit 1
}

if [[ "${OPERATION}" == "migrate" ]]; then
  trap cleanup_migration_candidate EXIT
  API_COMPOSE_FILE="$(basename "${CANDIDATE_FILE}")" bash "${MIGRATION_SCRIPT}"
  trap - EXIT
  transaction cleanup
  exit 0
fi

trap cleanup_candidate_only EXIT
exec 9>"${DEPLOY_LOCK_FILE}"
flock -n 9 || {
  echo "another deployment holds ${DEPLOY_LOCK_FILE}" >&2
  exit 1
}
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

API_COMPOSE_FILE="$(basename "${CANDIDATE_FILE}")" \
  API_DEPLOY_LOCK_ALREADY_HELD=true \
bash "${DEPLOY_SCRIPT}"
transaction promote
trap - EXIT
[[ -z "${ROLE_AGENT_BACKUP}" ]] || rm -f -- "${ROLE_AGENT_BACKUP}" \
  || echo "warning: stale Patroni role agent backup remains at ${ROLE_AGENT_BACKUP}" >&2
[[ -z "${ROLE_IDENTITY_BACKUP}" ]] || rm -f -- "${ROLE_IDENTITY_BACKUP}" \
  || echo "warning: stale Patroni identity backup remains at ${ROLE_IDENTITY_BACKUP}" >&2
