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
FORCE_COMPOSE_RECONCILE_ON_NOOP="${API_FORCE_COMPOSE_RECONCILE_ON_NOOP:-false}"
GOOGLE_TOKEN_CONTRACT_LABEL="org.mvn.google-oauth-token-contract"
GOOGLE_TOKEN_CONTRACT_REQUIRED="directory-v1"
GOOGLE_ROLLBACK_PROBE_REQUIRED="${API_GOOGLE_ROLLBACK_PROBE_REQUIRED:-true}"

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

reconcile_current_compose() {
  local service active_slot
  local resolved_services=()
  [[ "${current_image}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]] || {
    echo "Cannot reconcile compose without an immutable current image" >&2
    return 1
  }
  read -r -a requested_services <<<"${DEPLOY_SERVICES}"
  for service in "${requested_services[@]}"; do
    if [[ "${service}" == "app" && -f "${ACTIVE_SLOT_FILE}" ]]; then
      active_slot="$(tr -d '\r\n' < "${ACTIVE_SLOT_FILE}")"
      case "${active_slot}" in
        blue|green) service="app-${active_slot}" ;;
        *) echo "Invalid active API slot: ${active_slot}" >&2; return 1 ;;
      esac
    fi
    resolved_services+=("${service}")
  done
  export BACKEND_IMAGE="${current_image}"
  docker compose -f "${COMPOSE_FILE}" --profile bluegreen \
    up -d --no-deps --force-recreate "${resolved_services[@]}"
  for _ in $(seq 1 30); do
    if curl -fsS "${READY_URL}" >/tmp/mvn-backend-compose-reconcile.out; then
      cat /tmp/mvn-backend-compose-reconcile.out
      printf '\n'
      echo "Canonical compose runtime reconciled"
      return 0
    fi
    sleep 2
  done
  echo "Canonical compose runtime did not become healthy" >&2
  return 1
}

resolve_active_app_service() {
  local service="app"
  local active_slot=""
  if [[ -f "${ACTIVE_SLOT_FILE}" ]]; then
    active_slot="$(tr -d '\r\n' < "${ACTIVE_SLOT_FILE}")"
    case "${active_slot}" in
      blue|green) service="app-${active_slot}" ;;
      *) echo "Invalid active API slot: ${active_slot}" >&2; return 1 ;;
    esac
  fi
  printf '%s\n' "${service}"
}

probe_google_backups() {
  local app_service
  [[ "${GOOGLE_ROLLBACK_PROBE_REQUIRED}" == "true" ]] || return 0
  app_service="$(resolve_active_app_service)"
  docker compose -f "${COMPOSE_FILE}" --profile bluegreen exec -T "${app_service}" \
    python3 - <<'PY'
from services.backup_service import backup_service
from services.google_service import get_google_service
import os
import tempfile
from pathlib import Path

google = get_google_service()
token_file = Path(os.environ["GOOGLE_TOKEN_FILE"])
probe_path = token_file.parent / ".rollback-write-probe"
fd, temporary = tempfile.mkstemp(dir=token_file.parent, prefix=".rollback-write-probe.")
try:
    with os.fdopen(fd, "wb") as handle:
        handle.write(b"ok")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, probe_path)
    temporary = ""
    probe_path.unlink()
    directory_fd = os.open(token_file.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
finally:
    if temporary:
        Path(temporary).unlink(missing_ok=True)
    probe_path.unlink(missing_ok=True)
# Listing forces credential load/refresh and retries persistence after a
# transient write failure before the durable-auth verdict is evaluated.
items = backup_service.list_backups(limit=1)
if not items:
    raise SystemExit("Google backup probe returned no backup objects")
status = google.get_token_status()
if google.auth_error is not None or status.get("persistence_ok") is not True:
    raise SystemExit("Google OAuth persistence is not healthy")
print(f"google_backup_probe=passed items={len(items)}")
PY
}

restore_current_image_after_failed_probe() {
  echo "Google backup probe failed; restoring the previously active image." >&2
  if [[ -f "${ACTIVE_SLOT_FILE}" ]]; then
    BACKEND_IMAGE="${current_image}" \
      API_RUN_MIGRATIONS=false \
      API_RUN_DEFAULTS=false \
      API_DRAIN_SECONDS=0 \
      API_DEPLOY_LOCK_ALREADY_HELD=true \
      bash "${BLUE_GREEN_SCRIPT}"
    return
  fi
  write_backend_image "${current_image}"
  reconcile_current_compose
}

restore_current_image_or_critical() {
  if restore_current_image_after_failed_probe; then
    echo "Previously active image restored after failed Google backup probe." >&2
    return 0
  fi
  echo "CRITICAL: Google backup probe failed and the previously active image could not be restored." >&2
  return 90
}

if [[ -n "${EXPECTED_CURRENT_IMAGE}" && "${current_image}" != "${EXPECTED_CURRENT_IMAGE}" ]]; then
  if [[ "${FORCE_COMPOSE_RECONCILE_ON_NOOP}" == "true" ]]; then
    echo "Candidate was not activated; reconciling current image with restored canonical compose."
    reconcile_current_compose
    exit 0
  fi
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
if [[ ! "${current_image}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]]; then
  echo "Refusing rollback without an immutable currently active image for recovery." >&2
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

if ! docker image inspect "${ROLLBACK_TARGET}" >/dev/null 2>&1; then
  echo "Pulling rollback image: ${ROLLBACK_TARGET}"
  docker pull "${ROLLBACK_TARGET}"
fi
target_contract="$(
  docker image inspect \
    --format '{{ index .Config.Labels "org.mvn.google-oauth-token-contract" }}' \
    "${ROLLBACK_TARGET}"
)"
if [[ "${target_contract}" != "${GOOGLE_TOKEN_CONTRACT_REQUIRED}" ]]; then
  echo "Refusing rollback: target image does not declare ${GOOGLE_TOKEN_CONTRACT_LABEL}=${GOOGLE_TOKEN_CONTRACT_REQUIRED}." >&2
  echo "Pre-hotfix images cannot durably refresh Google OAuth credentials; use a normal roll-forward release." >&2
  exit 1
fi
if [[ -L "${COMPOSE_FILE}" || ! -f "${COMPOSE_FILE}" ]] \
  || ! grep -Fq '/app/google-oauth' "${COMPOSE_FILE}" \
  || ! grep -Eq 'GOOGLE_TOKEN_FILE(:[[:space:]]*|=)/app/google-oauth/token\.json' "${COMPOSE_FILE}" \
  || grep -Fq '/app/token.json' "${COMPOSE_FILE}"; then
  echo "Refusing rollback: canonical compose does not provide the directory-v1 Google token contract." >&2
  exit 1
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
  if ! probe_google_backups; then
    restore_current_image_or_critical || exit $?
    exit 1
  fi
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
    if ! probe_google_backups; then
      restore_current_image_or_critical || exit $?
      exit 1
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
  if ! reconcile_current_compose; then
    echo "CRITICAL: rollback target and previously active image both failed readiness." >&2
    exit 90
  fi
fi
exit 1
