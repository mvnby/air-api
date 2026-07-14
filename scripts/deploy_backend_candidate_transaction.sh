#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
CANONICAL_FILE="${API_CANONICAL_COMPOSE_FILE:-${PROJECT_DIR}/docker-compose.prod.yml}"
CANDIDATE_FILE="${API_CANDIDATE_COMPOSE_FILE:-}"
TRANSACTION_ENABLED="${API_COMPOSE_TRANSACTIONAL:-true}"
DEPLOY_STRATEGY="${API_DEPLOY_STRATEGY:-blue_green}"
TRANSACTION_SCRIPT="${COMPOSE_CANDIDATE_TRANSACTION_SCRIPT:-${SCRIPT_DIR}/compose_candidate_transaction.sh}"
BLUE_GREEN_SCRIPT="${API_BLUE_GREEN_SCRIPT:-${SCRIPT_DIR}/deploy_backend_blue_green.sh}"
IN_PLACE_SCRIPT="${API_IN_PLACE_DEPLOY_SCRIPT:-${SCRIPT_DIR}/deploy.sh}"
SMOKE_SCRIPT="${API_SMOKE_SCRIPT:-${SCRIPT_DIR}/post_deploy_smoke_check.sh}"
RECONCILE_SCRIPT="${API_RECONCILE_SCRIPT:-${SCRIPT_DIR}/reconcile_backend_compose_runtime.sh}"
DEPLOY_LOCK_FILE="${API_DEPLOY_LOCK_FILE:-${PROJECT_DIR}/.deploy.lock}"
DEPLOY_LOCK_FD="${API_DEPLOY_LOCK_FD:-}"
DEPLOY_LOCK_HELPER="${API_DEPLOY_LOCK_HELPER:-${SCRIPT_DIR}/ha/safe_deploy_lock.py}"
DEPLOY_LOCK_HELPER_SHA256="${API_DEPLOY_LOCK_HELPER_SHA256:-}"
STOP_SERVICES_AFTER_DEPLOY="${API_STOP_SERVICES_AFTER_DEPLOY:-}"
ACTIVE_SLOT_FILE="${API_ACTIVE_SLOT_FILE:-${PROJECT_DIR}/.active-api-slot}"
PREVIOUS_BACKEND_IMAGE="${API_PREVIOUS_BACKEND_IMAGE:-}"
CANDIDATE_CHECKSUM=""

transaction() {
  CANONICAL_COMPOSE_FILE="${CANONICAL_FILE}" \
    CANDIDATE_COMPOSE_FILE="${CANDIDATE_FILE}" \
    bash "${TRANSACTION_SCRIPT}" "$1"
}

cleanup_candidate_only() {
  local status=$?
  trap - EXIT
  set +e
  if [[ "${TRANSACTION_ENABLED}" == "true" ]]; then
    transaction cleanup
  fi
  exit "${status}"
}

failed_candidate() {
  local status=$?
  local restoration_failed=false
  trap - EXIT
  set +e
  if promotion_committed; then
    echo "candidate compose promotion committed; preserving the consistent new runtime" >&2
    exit "${status}"
  fi
  if [[ "${TRANSACTION_ENABLED}" == "true" ]]; then
    transaction cleanup || restoration_failed=true
  fi
  if ! API_COMPOSE_FILE="$(basename "${CANONICAL_FILE}")" \
    API_RECONCILE_BACKEND_IMAGE="${PREVIOUS_BACKEND_IMAGE}" \
    bash "${RECONCILE_SCRIPT}"; then
    restoration_failed=true
  fi
  if [[ "${restoration_failed}" == "true" ]]; then
    echo "CRITICAL: failed candidate could not be fully restored to canonical runtime" >&2
    exit 90
  fi
  exit "${status}"
}

promotion_committed() {
  local canonical_checksum=""
  [[ "${TRANSACTION_ENABLED}" == "true" ]] || return 1
  [[ -n "${CANDIDATE_CHECKSUM}" && ! -e "${CANDIDATE_FILE}" ]] || return 1
  [[ -f "${CANONICAL_FILE}" && ! -L "${CANONICAL_FILE}" ]] || return 1
  canonical_checksum="$(cksum < "${CANONICAL_FILE}")" || return 1
  [[ "${canonical_checksum}" == "${CANDIDATE_CHECKSUM}" ]]
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
    echo "could not resolve exactly one active backend container for rollback" >&2
    return 1
  }
  runtime_image="$(docker inspect --format '{{.Config.Image}}' "${container_ids}")"
  [[ "${runtime_image}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]] || {
    echo "active backend runtime image is not immutable" >&2
    return 1
  }
  PREVIOUS_BACKEND_IMAGE="${runtime_image}"
}

[[ "${TRANSACTION_ENABLED}" == "true" || "${TRANSACTION_ENABLED}" == "false" ]] || {
  echo "API_COMPOSE_TRANSACTIONAL must be true or false" >&2
  exit 1
}
if [[ "${TRANSACTION_ENABLED}" == "true" ]]; then
  [[ -n "${CANDIDATE_FILE}" && -f "${CANDIDATE_FILE}" ]] || {
    echo "candidate compose is required for transactional deploy" >&2
    exit 1
  }
  CANDIDATE_CHECKSUM="$(cksum < "${CANDIDATE_FILE}")"
else
  CANDIDATE_FILE="${CANONICAL_FILE}"
fi

mkdir -p "${PROJECT_DIR}"
trap cleanup_candidate_only EXIT
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
resolve_previous_backend_image

if [[ "${TRANSACTION_ENABLED}" == "true" ]]; then
  if ! transaction stage; then
    transaction cleanup || true
    exit 1
  fi
fi
trap failed_candidate EXIT

candidate_name="$(basename "${CANDIDATE_FILE}")"
case "${DEPLOY_STRATEGY}" in
  blue_green)
    API_COMPOSE_FILE="${candidate_name}" \
      API_DEPLOY_LOCK_FD="${DEPLOY_LOCK_FD}" \
      API_DEPLOY_LOCK_HELPER="${DEPLOY_LOCK_HELPER}" \
      API_DEPLOY_LOCK_HELPER_SHA256="${DEPLOY_LOCK_HELPER_SHA256}" \
      bash "${BLUE_GREEN_SCRIPT}"
    ;;
  in_place)
    API_COMPOSE_FILE="${candidate_name}" \
      API_DEPLOY_LOCK_FD="${DEPLOY_LOCK_FD}" \
      API_DEPLOY_LOCK_HELPER="${DEPLOY_LOCK_HELPER}" \
      API_DEPLOY_LOCK_HELPER_SHA256="${DEPLOY_LOCK_HELPER_SHA256}" \
      bash "${IN_PLACE_SCRIPT}"
    ;;
  *)
    echo "unsupported API_DEPLOY_STRATEGY=${DEPLOY_STRATEGY}" >&2
    exit 1
    ;;
esac

if [[ -n "${STOP_SERVICES_AFTER_DEPLOY}" ]]; then
  read -r -a stop_services <<<"${STOP_SERVICES_AFTER_DEPLOY}"
  docker compose -f "${CANDIDATE_FILE}" --profile bluegreen stop "${stop_services[@]}"
fi

COMPOSE_FILE="${CANDIDATE_FILE}" bash "${SMOKE_SCRIPT}"
if [[ "${TRANSACTION_ENABLED}" == "true" ]]; then
  transaction promote
fi
trap - EXIT
echo "backend candidate activation, smoke, and compose promotion completed"
