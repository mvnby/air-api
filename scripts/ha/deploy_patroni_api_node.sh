#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${API_COMPOSE_FILE:-docker-compose.patroni.yml}"
BACKEND_IMAGE="${BACKEND_IMAGE:-}"
EXPECTED_ROLE="${API_EXPECTED_PATRONI_ROLE:-}"
PATRONI_URL="${API_PATRONI_URL:-http://127.0.0.1:8008/patroni}"
READY_URL="${API_READY_URL:-http://127.0.0.1:18080/api/ready}"
HEALTH_URL="${API_HEALTH_URL:-http://127.0.0.1:18080/api/health}"
BLUE_GREEN_SCRIPT="${API_BLUE_GREEN_SCRIPT:-/tmp/deploy_backend_blue_green.sh}"
PROXY_MODE="${API_PROXY_MODE:-host_nginx}"
PROXY_SERVICE="${API_PROXY_SERVICE:-api-proxy}"
DEPLOY_LOCK_FILE="${API_DEPLOY_LOCK_FILE:-${PROJECT_DIR}/.deploy.lock}"
DEPLOY_LOCK_ALREADY_HELD="${API_DEPLOY_LOCK_ALREADY_HELD:-false}"
MAINTENANCE_MARKER="${API_MAINTENANCE_MARKER:-${PROJECT_DIR}/.patroni-cutover-in-progress}"
ACTIVE_SLOT_FILE="${API_ACTIVE_SLOT_FILE:-${PROJECT_DIR}/.active-api-slot}"
PREVIOUS_IMAGE_FILE="${PROJECT_DIR}/.previous-backend-image"
ENV_FILE="${PROJECT_DIR}/.env"
HEALTH_ATTEMPTS="${API_HEALTH_ATTEMPTS:-30}"
GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT="${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT:-${SCRIPT_DIR}/../prepare_google_oauth_token_dir.sh}"

previous_image=""
active_service="app"
env_updated=false
TMP_DIR=""

log() {
  printf '[patroni-node-deploy][%s] %s\n' "$1" "$2"
}

local_role() {
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

require_expected_role() {
  local role
  role="$(local_role)" || {
    log error "local Patroni API is unavailable"
    return 1
  }
  [[ "${role}" == "${EXPECTED_ROLE}" ]] || {
    log error "role changed: expected=${EXPECTED_ROLE} actual=${role}"
    return 1
  }
}

resolve_active_service() {
  local slot=""
  if [[ -f "${ACTIVE_SLOT_FILE}" ]]; then
    slot="$(tr -d '\r\n' < "${ACTIVE_SLOT_FILE}")"
    case "${slot}" in
      blue|green) active_service="app-${slot}" ;;
      *)
        log error "invalid active API slot: ${slot}"
        return 1
        ;;
    esac
  fi
}

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

wait_fenced_standby() {
  local health_file="${TMP_DIR}/health.json"
  local ready_file="${TMP_DIR}/ready.json"
  local ready_status=""

  for attempt in $(seq 1 "${HEALTH_ATTEMPTS}"); do
    ready_status="$(curl -sS --max-time 5 -o "${ready_file}" -w '%{http_code}' "${READY_URL}" || true)"
    if curl -fsS --max-time 5 "${HEALTH_URL}" > "${health_file}" \
      && [[ "${ready_status}" == "503" ]] \
      && python3 - "${health_file}" "${ready_file}" <<'PY'
import json
import sys

health = json.load(open(sys.argv[1], encoding="utf-8"))
ready = json.load(open(sys.argv[2], encoding="utf-8"))
if health.get("status") != "ok" or health.get("database") != "online":
    raise SystemExit(1)
if ready.get("api") != "not_ready" or ready.get("traffic") != "disabled":
    raise SystemExit(1)
PY
    then
      log smoke "standby is healthy and fenced on attempt ${attempt}"
      return 0
    fi
    sleep 2
  done
  log error "standby did not become healthy and fenced"
  return 1
}

reconcile_standby_proxy() {
  if [[ "${PROXY_MODE}" != "container_nginx" ]]; then
    return 0
  fi

  log standby "validating desired container proxy configuration"
  "${COMPOSE[@]}" run -T --rm --no-deps "${PROXY_SERVICE}" nginx -t
  "${COMPOSE[@]}" up -d --no-deps "${PROXY_SERVICE}"
  if ! "${COMPOSE[@]}" exec -T "${PROXY_SERVICE}" nginx -t; then
    log standby "running proxy has stale mounts; recreating fenced proxy"
    "${COMPOSE[@]}" up -d --no-deps --force-recreate "${PROXY_SERVICE}"
    "${COMPOSE[@]}" exec -T "${PROXY_SERVICE}" nginx -t
  fi
}

rollback_standby() {
  local exit_code=$?
  trap - ERR
  set +e
  if [[ "${env_updated}" == "true" && "${previous_image}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]]; then
    log rollback "restoring ${previous_image} on ${active_service}"
    export BACKEND_IMAGE="${previous_image}"
    write_backend_image "${previous_image}"
    "${COMPOSE[@]}" up -d --no-deps --force-recreate "${active_service}"
  fi
  "${COMPOSE[@]}" stop bot >/dev/null 2>&1 || true
  exit "${exit_code}"
}

for command in docker curl python3 flock; do
  command -v "${command}" >/dev/null 2>&1 || {
    log error "required command is missing: ${command}"
    exit 1
  }
done
[[ "${EXPECTED_ROLE}" == "primary" || "${EXPECTED_ROLE}" == "standby" ]] || {
  log error "API_EXPECTED_PATRONI_ROLE must be primary or standby"
  exit 1
}
[[ "${PROXY_MODE}" == "host_nginx" || "${PROXY_MODE}" == "container_nginx" ]] || {
  log error "API_PROXY_MODE must be host_nginx or container_nginx"
  exit 1
}
[[ "${BACKEND_IMAGE}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]] || {
  log error "BACKEND_IMAGE must be immutable"
  exit 1
}
[[ ! -e "${MAINTENANCE_MARKER}" ]] || {
  log error "Patroni maintenance marker exists: ${MAINTENANCE_MARKER}"
  exit 1
}
[[ -f "${PROJECT_DIR}/${COMPOSE_FILE}" ]] || {
  log error "compose file is missing: ${PROJECT_DIR}/${COMPOSE_FILE}"
  exit 1
}

cd "${PROJECT_DIR}"
if [[ "${DEPLOY_LOCK_ALREADY_HELD}" != "true" ]]; then
  exec 9>"${DEPLOY_LOCK_FILE}"
  flock -n 9 || {
    log error "another deployment holds ${DEPLOY_LOCK_FILE}"
    exit 1
  }
fi
require_expected_role
[[ -f "${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT}" ]] || {
  log error "Google OAuth token preparation script is missing: ${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT}"
  exit 1
}
GOOGLE_OAUTH_PROJECT_DIR="${PROJECT_DIR}" \
  bash "${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT}" prepare

if [[ "${EXPECTED_ROLE}" == "primary" ]]; then
  [[ -x "${BLUE_GREEN_SCRIPT}" ]] || {
    log error "blue-green script is not executable: ${BLUE_GREEN_SCRIPT}"
    exit 1
  }
  log primary "deploying through the inactive API slot"
  API_DEPLOY_LOCK_ALREADY_HELD=true \
    API_RUN_MIGRATIONS=false \
    API_RUN_DEFAULTS=false \
    bash "${BLUE_GREEN_SCRIPT}"
  require_expected_role
  log "done" "primary blue-green deployment completed"
  exit 0
fi

resolve_active_service
previous_image="$(sed -n 's/^BACKEND_IMAGE=//p' "${ENV_FILE}" | tail -n 1)"
[[ "${previous_image}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]] || {
  log error "current BACKEND_IMAGE is not immutable"
  exit 1
}

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT
COMPOSE=(docker compose -f "${COMPOSE_FILE}" --profile bluegreen)
export BACKEND_IMAGE
if [[ -n "${GHCR_PAT:-}" ]]; then
  printf '%s' "${GHCR_PAT}" | docker login ghcr.io -u "${GITHUB_ACTOR:-github-actions}" --password-stdin
fi

trap rollback_standby ERR
reconcile_standby_proxy
log standby "updating fenced service ${active_service}"
"${COMPOSE[@]}" pull "${active_service}" bot
write_backend_image "${BACKEND_IMAGE}"
env_updated=true
"${COMPOSE[@]}" stop bot >/dev/null 2>&1 || true
"${COMPOSE[@]}" up -d --no-deps --force-recreate "${active_service}"
require_expected_role
wait_fenced_standby
printf '%s\n' "${previous_image}" > "${PREVIOUS_IMAGE_FILE}"
chmod 600 "${PREVIOUS_IMAGE_FILE}"
trap - ERR
log "done" "standby image updated without enabling traffic or singleton processes"
