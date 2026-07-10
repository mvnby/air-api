#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${API_COMPOSE_FILE:-docker-compose.prod.yml}"
DEPLOY_SERVICES="${API_DEPLOY_SERVICES:-app bot}"
READY_URL="${API_READY_URL:-http://127.0.0.1:8000/api/ready}"
ROLLBACK_TARGET="${BACKEND_ROLLBACK_TARGET:-}"
EXPECTED_CURRENT_IMAGE="${EXPECTED_CURRENT_IMAGE:-}"
CONFIRM_ROLLBACK="${CONFIRM_ROLLBACK:-false}"
DEPLOY_LOCK_FILE="${API_DEPLOY_LOCK_FILE:-${PROJECT_DIR}/.deploy.lock}"
ACTIVE_SLOT_FILE="${API_ACTIVE_SLOT_FILE:-${PROJECT_DIR}/.active-api-slot}"
BLUE_GREEN_SCRIPT="${API_BLUE_GREEN_SCRIPT:-/tmp/deploy_backend_blue_green.sh}"

usage() {
  cat <<'USAGE'
Usage: rollback_backend.sh [--target IMAGE] [--yes]

Performs a code-only rollback. It does not downgrade the database schema, so
production migrations must follow the expand/contract compatibility policy.
USAGE
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --target)
      ROLLBACK_TARGET="${2:-}"
      shift 2
      ;;
    --yes)
      CONFIRM_ROLLBACK=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unsupported argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ "${CONFIRM_ROLLBACK}" != "true" ]]; then
  echo "Refusing rollback without CONFIRM_ROLLBACK=true or --yes" >&2
  exit 1
fi

cd "${PROJECT_DIR}"
if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "Compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}" >&2
  exit 1
fi

exec 9>"${DEPLOY_LOCK_FILE}"
if ! flock -n 9; then
  echo "Another deployment holds ${DEPLOY_LOCK_FILE}; refusing to overlap" >&2
  exit 1
fi

ENV_FILE="${PROJECT_DIR}/.env"
PREVIOUS_IMAGE_FILE="${PROJECT_DIR}/.previous-backend-image"
touch "${ENV_FILE}"
current_image="$(sed -n 's/^BACKEND_IMAGE=//p' "${ENV_FILE}" | tail -n 1)"
if [[ -n "${EXPECTED_CURRENT_IMAGE}" && "${current_image}" != "${EXPECTED_CURRENT_IMAGE}" ]]; then
  echo "Candidate was not activated; current image is ${current_image:-unset}. Nothing to roll back."
  exit 0
fi
if [[ -z "${ROLLBACK_TARGET}" && -f "${PREVIOUS_IMAGE_FILE}" ]]; then
  ROLLBACK_TARGET="$(tr -d '\r\n' < "${PREVIOUS_IMAGE_FILE}")"
fi
if [[ -z "${ROLLBACK_TARGET}" ]]; then
  echo "No rollback target supplied and ${PREVIOUS_IMAGE_FILE} is empty" >&2
  exit 1
fi
if [[ ! "${ROLLBACK_TARGET}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]]; then
  echo "Rollback target must use a 40-character Git SHA tag or sha256 digest" >&2
  exit 1
fi
if [[ "${ROLLBACK_TARGET}" == "${current_image}" ]]; then
  echo "Rollback target is already active: ${ROLLBACK_TARGET}"
  exit 0
fi

if [[ -f "${ACTIVE_SLOT_FILE}" ]]; then
  if [[ ! -x "${BLUE_GREEN_SCRIPT}" ]]; then
    echo "Blue-green rollback requires executable ${BLUE_GREEN_SCRIPT}" >&2
    exit 1
  fi
  echo "Deploying rollback target through the inactive API slot: ${ROLLBACK_TARGET}"
  BACKEND_IMAGE="${ROLLBACK_TARGET}" \
    API_RUN_MIGRATIONS=false \
    API_RUN_DEFAULTS=false \
    API_DRAIN_SECONDS=0 \
    API_DEPLOY_LOCK_ALREADY_HELD=true \
    bash "${BLUE_GREEN_SCRIPT}"
  exit 0
fi

write_backend_image() {
  local image="$1"
  local tmp
  tmp="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"
  grep -v '^BACKEND_IMAGE=' "${ENV_FILE}" > "${tmp}" || true
  printf 'BACKEND_IMAGE=%s\n' "${image}" >> "${tmp}"
  chmod --reference="${ENV_FILE}" "${tmp}" 2>/dev/null || chmod 600 "${tmp}"
  chown --reference="${ENV_FILE}" "${tmp}" 2>/dev/null || true
  mv "${tmp}" "${ENV_FILE}"
}

if ! docker image inspect "${ROLLBACK_TARGET}" >/dev/null 2>&1; then
  echo "Pulling rollback image: ${ROLLBACK_TARGET}"
  docker pull "${ROLLBACK_TARGET}"
fi

read -r -a deploy_services <<<"${DEPLOY_SERVICES}"
COMPOSE=(docker compose -f "${COMPOSE_FILE}")
export BACKEND_IMAGE="${ROLLBACK_TARGET}"
write_backend_image "${ROLLBACK_TARGET}"

echo "Recreating application services with rollback image: ${ROLLBACK_TARGET}"
"${COMPOSE[@]}" up -d --no-deps --force-recreate "${deploy_services[@]}"

for _ in $(seq 1 30); do
  if curl -fsS "${READY_URL}" >/tmp/mvn-backend-rollback-ready.out; then
    cat /tmp/mvn-backend-rollback-ready.out
    printf '\n'
    if [[ -n "${current_image}" ]]; then
      printf '%s\n' "${current_image}" > "${PREVIOUS_IMAGE_FILE}"
      chmod 600 "${PREVIOUS_IMAGE_FILE}"
    fi
    echo "Backend rollback completed"
    exit 0
  fi
  sleep 2
done

"${COMPOSE[@]}" logs --tail=120 app || true
if [[ -n "${current_image}" ]]; then
  echo "Rollback target failed readiness; restoring ${current_image}" >&2
  export BACKEND_IMAGE="${current_image}"
  write_backend_image "${current_image}"
  "${COMPOSE[@]}" up -d --no-deps --force-recreate "${deploy_services[@]}" || true
fi
exit 1
