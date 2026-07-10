#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${API_COMPOSE_FILE:-docker-compose.patroni.yml}"
BACKEND_IMAGE="${BACKEND_IMAGE:-}"
MIGRATION_SERVICE="${API_MIGRATION_SERVICE:-app-blue}"
PATRONI_URL="${API_PATRONI_URL:-http://127.0.0.1:8008/patroni}"
DEPLOY_LOCK_FILE="${API_DEPLOY_LOCK_FILE:-${PROJECT_DIR}/.deploy.lock}"
MAINTENANCE_MARKER="${API_MAINTENANCE_MARKER:-${PROJECT_DIR}/.patroni-cutover-in-progress}"
RUN_DEFAULTS="${API_RUN_DEFAULTS:-true}"

log() {
  printf '[patroni-migrate][%s] %s\n' "$1" "$2"
}

local_role() {
  curl -fsS --max-time 5 "${PATRONI_URL}" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
if payload.get("state") != "running":
    raise SystemExit(1)
role = str(payload.get("role") or "").lower()
print("primary" if role in {"leader", "master", "primary"} else "standby")
'
}

require_primary() {
  local role
  role="$(local_role)" || {
    log error "local Patroni API is unavailable"
    return 1
  }
  [[ "${role}" == "primary" ]] || {
    log error "refusing migrations on local role=${role}"
    return 1
  }
}

for command in docker curl python3 flock; do
  command -v "${command}" >/dev/null 2>&1 || {
    log error "required command is missing: ${command}"
    exit 1
  }
done
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
exec 9>"${DEPLOY_LOCK_FILE}"
flock -n 9 || {
  log error "another deployment holds ${DEPLOY_LOCK_FILE}"
  exit 1
}

require_primary
export BACKEND_IMAGE
COMPOSE=(docker compose -f "${COMPOSE_FILE}" --profile bluegreen)
if [[ -n "${GHCR_PAT:-}" ]]; then
  printf '%s' "${GHCR_PAT}" | docker login ghcr.io -u "${GITHUB_ACTOR:-github-actions}" --password-stdin
fi

log pull "pulling migration image ${BACKEND_IMAGE}"
"${COMPOSE[@]}" pull "${MIGRATION_SERVICE}"
require_primary

log migrate "running Alembic on the confirmed Patroni primary"
"${COMPOSE[@]}" run -T --rm --no-deps "${MIGRATION_SERVICE}" alembic upgrade head
if [[ "${RUN_DEFAULTS}" == "true" ]]; then
  "${COMPOSE[@]}" run -T --rm --no-deps "${MIGRATION_SERVICE}" \
    python3 scripts/ensure_global_config_defaults.py
fi

require_primary
log "done" "migrations completed while the local node remained primary"
