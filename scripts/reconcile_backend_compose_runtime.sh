#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${API_COMPOSE_FILE:-docker-compose.prod.yml}"
DEPLOY_SERVICES="${API_DEPLOY_SERVICES:-app bot}"
ACTIVE_SLOT_FILE="${API_ACTIVE_SLOT_FILE:-${PROJECT_DIR}/.active-api-slot}"
HEALTH_URL="${API_READY_URL:-http://127.0.0.1:8000/api/health}"
HEALTH_ATTEMPTS="${API_HEALTH_ATTEMPTS:-30}"
STOP_SERVICES="${API_STOP_SERVICES_AFTER_DEPLOY:-}"
ENV_FILE="${API_ENV_FILE:-${PROJECT_DIR}/.env}"
RECONCILE_BACKEND_IMAGE="${API_RECONCILE_BACKEND_IMAGE:-}"

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
if [[ -n "${RECONCILE_BACKEND_IMAGE}" ]]; then
  write_backend_image "${BACKEND_IMAGE}"
fi
export BACKEND_IMAGE

read -r -a requested_services <<<"${DEPLOY_SERVICES}"
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

docker compose -f "${COMPOSE_FILE}" --profile bluegreen \
  up -d --no-deps --force-recreate "${resolved_services[@]}"
if [[ -n "${STOP_SERVICES}" ]]; then
  read -r -a stop_services <<<"${STOP_SERVICES}"
  docker compose -f "${COMPOSE_FILE}" --profile bluegreen stop "${stop_services[@]}"
fi

for _ in $(seq 1 "${HEALTH_ATTEMPTS}"); do
  if curl -fsS "${HEALTH_URL}" >/tmp/mvn-canonical-compose-health.out; then
    cat /tmp/mvn-canonical-compose-health.out
    printf '\n'
    echo "canonical compose runtime reconciled"
    exit 0
  fi
  sleep 2
done
echo "canonical compose runtime did not become healthy" >&2
exit 1
