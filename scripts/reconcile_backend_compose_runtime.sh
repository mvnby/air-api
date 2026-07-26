#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${API_COMPOSE_FILE:-docker-compose.prod.yml}"
DEPLOY_SERVICES="${API_DEPLOY_SERVICES:-app}"
ACTIVE_SLOT_FILE="${API_ACTIVE_SLOT_FILE:-${PROJECT_DIR}/.active-api-slot}"
HEALTH_URL="${API_READY_URL:-http://127.0.0.1:8000/api/health}"
HEALTH_ATTEMPTS="${API_HEALTH_ATTEMPTS:-30}"
STOP_SERVICES="${API_STOP_SERVICES_AFTER_DEPLOY:-}"
ENV_FILE="${API_ENV_FILE:-${PROJECT_DIR}/.env}"
RECONCILE_BACKEND_IMAGE="${API_RECONCILE_BACKEND_IMAGE:-}"
COMMUNICATIONS_WORKER_SERVICE="${API_COMMUNICATIONS_WORKER_SERVICE:-communications-worker}"
RECONCILE_OPERATION="${API_RECONCILE_OPERATION:-reconcile}"
EXPECTED_ROLE="${API_EXPECTED_PATRONI_ROLE:-}"
COMMUNICATIONS_WORKER_RELEASE_HELPER="${COMMUNICATIONS_WORKER_RELEASE_HELPER:-${SCRIPT_DIR}/ha/communications_worker_release_contract.sh}"

write_backend_image() {
  local image="$1"
  local temporary

  touch "${ENV_FILE}"
  temporary="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"
  grep -v '^BACKEND_IMAGE=' "${ENV_FILE}" > "${temporary}" || true
  printf 'BACKEND_IMAGE=%s\n' "${image}" >> "${temporary}"
  chmod --reference="${ENV_FILE}" "${temporary}" 2>/dev/null || chmod 600 "${temporary}"
  chown --reference="${ENV_FILE}" "${temporary}" 2>/dev/null || true
  mv "${temporary}" "${ENV_FILE}"
}

[[ "${RECONCILE_OPERATION}" == "reconcile" || "${RECONCILE_OPERATION}" == "verify" ]] || {
  echo "API_RECONCILE_OPERATION must be reconcile or verify" >&2
  exit 2
}
requested_communications_worker=false
read -r -a requested_services <<<"${DEPLOY_SERVICES}"
for requested_service in "${requested_services[@]}"; do
  if [[ "${requested_service}" == "${COMMUNICATIONS_WORKER_SERVICE}" ]]; then
    requested_communications_worker=true
  fi
done
if [[ "${requested_communications_worker}" == "true" ]]; then
  [[ -f "${COMMUNICATIONS_WORKER_RELEASE_HELPER}" \
    && ! -L "${COMMUNICATIONS_WORKER_RELEASE_HELPER}" ]] || {
    echo "communications worker release helper is missing or unsafe" >&2
    exit 1
  }
  # shellcheck disable=SC1090
  source "${COMMUNICATIONS_WORKER_RELEASE_HELPER}"
fi

cd "${PROJECT_DIR}"
[[ -f "${COMPOSE_FILE}" ]] || {
  echo "canonical compose is missing: ${PROJECT_DIR}/${COMPOSE_FILE}" >&2
  exit 1
}
if [[ -n "${RECONCILE_BACKEND_IMAGE}" ]]; then
  BACKEND_IMAGE="${RECONCILE_BACKEND_IMAGE}"
else
  BACKEND_IMAGE="$(sed -n 's/^BACKEND_IMAGE=//p' "${ENV_FILE}" | tail -n 1)"
fi
[[ "${BACKEND_IMAGE}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]] || {
  echo "canonical reconcile requires an immutable BACKEND_IMAGE" >&2
  exit 1
}
export BACKEND_IMAGE

resolved_services=()
for service in "${requested_services[@]}"; do
  if [[ "${service}" == "app" && -f "${ACTIVE_SLOT_FILE}" ]]; then
    active_slot="$(tr -d '\r\n' < "${ACTIVE_SLOT_FILE}")"
    case "${active_slot}" in
      blue|green) service="app-${active_slot}" ;;
      *) echo "invalid active API slot: ${active_slot}" >&2; exit 1 ;;
    esac
  fi
  resolved_services+=("${service}")
done

COMPOSE=(docker compose -f "${COMPOSE_FILE}" --profile bluegreen)
# shellcheck disable=SC2329  # invoked by the ERR trap
reconcile_failure() {
  local status=$?
  trap - ERR
  set +e
  if [[ "${requested_communications_worker}" == "true" ]]; then
    communications_worker_set_release_fence
    "${COMPOSE[@]}" stop "${COMMUNICATIONS_WORKER_SERVICE}" >/dev/null 2>&1
  fi
  exit "${status}"
}
trap reconcile_failure ERR
if [[ "${requested_communications_worker}" == "true" ]]; then
  communications_worker_require_contract
fi
if [[ "${RECONCILE_OPERATION}" == "verify" ]]; then
  [[ "${requested_communications_worker}" == "true" ]] || {
    echo "verify operation requires ${COMMUNICATIONS_WORKER_SERVICE}" >&2
    exit 2
  }
  communications_worker_require_runtime "${EXPECTED_ROLE}"
  echo "canonical communications worker runtime verified"
  exit 0
fi
if [[ "${requested_communications_worker}" == "true" ]]; then
  communications_worker_set_release_fence
  "${COMPOSE[@]}" stop "${COMMUNICATIONS_WORKER_SERVICE}" >/dev/null
fi
if [[ -n "${RECONCILE_BACKEND_IMAGE}" ]]; then
  write_backend_image "${BACKEND_IMAGE}"
fi

app_services=()
for service in "${resolved_services[@]}"; do
  if [[ "${service}" != "${COMMUNICATIONS_WORKER_SERVICE}" ]]; then
    app_services+=("${service}")
  fi
done
if [[ "${#app_services[@]}" -gt 0 ]]; then
  "${COMPOSE[@]}" up -d --no-deps --force-recreate "${app_services[@]}"
fi
if [[ "${requested_communications_worker}" == "true" ]]; then
  communications_worker_start_controlled "${EXPECTED_ROLE}"
fi
if [[ -n "${STOP_SERVICES}" ]]; then
  read -r -a stop_services <<<"${STOP_SERVICES}"
  "${COMPOSE[@]}" stop "${stop_services[@]}"
fi
for _ in $(seq 1 "${HEALTH_ATTEMPTS}"); do
  if curl -fsS "${HEALTH_URL}" >/tmp/mvn-canonical-compose-health.out; then
    cat /tmp/mvn-canonical-compose-health.out
    printf '\n'
    echo "canonical compose runtime reconciled"
    trap - ERR
    exit 0
  fi
  sleep 2
done
echo "canonical compose runtime did not become healthy" >&2
exit 1
