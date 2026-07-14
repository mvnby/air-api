#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${API_COMPOSE_FILE:-docker-compose.patroni.yml}"
BACKEND_IMAGE="${BACKEND_IMAGE:-}"
MIGRATION_SERVICE="${API_MIGRATION_SERVICE:-app-blue}"
PATRONI_URL="${API_PATRONI_URL:-http://127.0.0.1:8008/patroni}"
DEPLOY_LOCK_FILE="${API_DEPLOY_LOCK_FILE:-${PROJECT_DIR}/.deploy.lock}"
MAINTENANCE_MARKER="${API_MAINTENANCE_MARKER:-${PROJECT_DIR}/.patroni-cutover-in-progress}"
PITR_MAINTENANCE_MARKER="${API_PITR_MAINTENANCE_MARKER:-/run/mvn-postgres-pitr-maintenance}"
RUN_DEFAULTS="${API_RUN_DEFAULTS:-true}"
CAPACITY_HELPER="${API_DEPLOY_CAPACITY_HELPER:-${SCRIPT_DIR}/require_deploy_capacity.sh}"
DEPLOY_LOCK_FD="${API_DEPLOY_LOCK_FD:-}"
DEPLOY_LOCK_HELPER="${API_DEPLOY_LOCK_HELPER:-${SCRIPT_DIR}/safe_deploy_lock.py}"
DEPLOY_LOCK_HELPER_SHA256="${API_DEPLOY_LOCK_HELPER_SHA256:-}"
GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT="${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT:-${SCRIPT_DIR}/../prepare_google_oauth_token_dir.sh}"

log() {
  printf '[patroni-migrate][%s] %s\n' "$1" "$2"
}

[[ "${DEPLOY_LOCK_HELPER_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
  log error "safe deployment lock helper digest is missing"; exit 1;
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
  log error "migration requires inherited deployment lock fd 9"
  exit 1
}
python3 "${DEPLOY_LOCK_HELPER}" verify "${DEPLOY_LOCK_FILE}" "${DEPLOY_LOCK_FD}"

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

for command in docker curl python3 awk; do
  command -v "${command}" >/dev/null 2>&1 || {
    log error "required command is missing: ${command}"
    exit 1
  }
done
[[ -f "${CAPACITY_HELPER}" && ! -L "${CAPACITY_HELPER}" ]] || {
  log error "deploy capacity helper is missing or unsafe: ${CAPACITY_HELPER}"
  exit 1
}
# shellcheck disable=SC1090
source "${CAPACITY_HELPER}"
[[ "${BACKEND_IMAGE}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]] || {
  log error "BACKEND_IMAGE must be immutable"
  exit 1
}
[[ ! -e "${MAINTENANCE_MARKER}" ]] || {
  log error "Patroni maintenance marker exists: ${MAINTENANCE_MARKER}"
  exit 1
}
[[ ! -e "${PITR_MAINTENANCE_MARKER}" && ! -L "${PITR_MAINTENANCE_MARKER}" ]] || {
  log error "PITR release maintenance is active: ${PITR_MAINTENANCE_MARKER}"
  exit 1
}
[[ -f "${PROJECT_DIR}/${COMPOSE_FILE}" ]] || {
  log error "compose file is missing: ${PROJECT_DIR}/${COMPOSE_FILE}"
  exit 1
}

cd "${PROJECT_DIR}"
[[ ! -e "${MAINTENANCE_MARKER}" && ! -L "${MAINTENANCE_MARKER}" ]] || {
  log error "Patroni maintenance marker exists: ${MAINTENANCE_MARKER}"
  exit 1
}

require_primary
require_deploy_capacity
[[ -f "${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT}" ]] || {
  log error "Google OAuth token preparation script is missing: ${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT}"
  exit 1
}
GOOGLE_OAUTH_PROJECT_DIR="${PROJECT_DIR}" \
  bash "${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT}" prepare
export BACKEND_IMAGE
COMPOSE=(docker compose -f "${COMPOSE_FILE}" --profile bluegreen)
if [[ -n "${GHCR_PAT:-}" ]]; then
  printf '%s' "${GHCR_PAT}" | docker login ghcr.io -u "${GITHUB_ACTOR:-github-actions}" --password-stdin
fi

log pull "pulling migration image ${BACKEND_IMAGE}"
"${COMPOSE[@]}" pull "${MIGRATION_SERVICE}"
require_primary
require_deploy_capacity

log migrate "running Alembic on the confirmed Patroni primary"
[[ ! -e "${MAINTENANCE_MARKER}" && ! -L "${MAINTENANCE_MARKER}" ]] || {
  log error "Patroni maintenance marker appeared before migrations"
  exit 1
}
"${COMPOSE[@]}" run -T --rm --no-deps "${MIGRATION_SERVICE}" alembic upgrade head
if [[ "${RUN_DEFAULTS}" == "true" ]]; then
  require_primary
  require_deploy_capacity
  "${COMPOSE[@]}" run -T --rm --no-deps "${MIGRATION_SERVICE}" \
    python3 scripts/ensure_global_config_defaults.py
fi

require_primary
log "done" "migrations completed while the local node remained primary"
