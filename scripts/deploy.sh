#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting deployment script on server..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${API_COMPOSE_FILE:-docker-compose.prod.yml}"
DEPLOY_SERVICES="${API_DEPLOY_SERVICES:-app}"
MIGRATION_SERVICE="${API_MIGRATION_SERVICE:-app}"
RUN_MIGRATIONS="${API_RUN_MIGRATIONS:-true}"
RUN_DEFAULTS="${API_RUN_DEFAULTS:-true}"
BACKEND_IMAGE="${BACKEND_IMAGE:-}"
DEPLOY_LOCK_FILE="${API_DEPLOY_LOCK_FILE:-${PROJECT_DIR}/.deploy.lock}"
DEPLOY_LOCK_ALREADY_HELD="${API_DEPLOY_LOCK_ALREADY_HELD:-false}"
DEPLOY_LOCK_FD="${API_DEPLOY_LOCK_FD:-}"
DEPLOY_LOCK_HELPER="${API_DEPLOY_LOCK_HELPER:-${SCRIPT_DIR}/ha/safe_deploy_lock.py}"
DEPLOY_LOCK_HELPER_SHA256="${API_DEPLOY_LOCK_HELPER_SHA256:-}"
GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT="${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT:-${SCRIPT_DIR}/prepare_google_oauth_token_dir.sh}"

if [[ ! "${BACKEND_IMAGE}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]]; then
    echo "❌ BACKEND_IMAGE must use a 40-character Git SHA tag or sha256 digest" >&2
    exit 1
fi
export BACKEND_IMAGE
echo "📌 Using immutable backend image: ${BACKEND_IMAGE}"

if [[ ! -d "${PROJECT_DIR}" ]]; then
    echo "❌ Project dir not found: ${PROJECT_DIR}"
    exit 1
fi

cd "${PROJECT_DIR}"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
    echo "❌ Compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}"
    exit 1
fi

if [[ "${DEPLOY_LOCK_ALREADY_HELD}" == "true" && -z "${DEPLOY_LOCK_FD}" ]]; then
    echo "❌ Legacy deploy-lock boolean cannot replace an inherited descriptor" >&2
    exit 1
fi
[[ "${DEPLOY_LOCK_HELPER_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
    echo "❌ Safe deployment lock helper digest is missing" >&2; exit 1;
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
    echo "❌ Deploy requires inherited deployment lock fd 9" >&2; exit 1;
}
python3 "${DEPLOY_LOCK_HELPER}" verify "${DEPLOY_LOCK_FILE}" "${DEPLOY_LOCK_FD}"

if [[ ! -f "${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT}" ]]; then
    echo "❌ Google OAuth token preparation script not found: ${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT}" >&2
    exit 1
fi
GOOGLE_OAUTH_PROJECT_DIR="${PROJECT_DIR}" \
    bash "${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT}" prepare

COMPOSE=(docker compose -f "${COMPOSE_FILE}")
read -r -a deploy_services <<<"${DEPLOY_SERVICES}"
if [[ "${#deploy_services[@]}" -eq 0 ]]; then
    echo "❌ API_DEPLOY_SERVICES resolved to an empty list" >&2
    exit 1
fi

pull_services=("${deploy_services[@]}")
migration_service_included=false
for service in "${pull_services[@]}"; do
    if [[ "${service}" == "${MIGRATION_SERVICE}" ]]; then
        migration_service_included=true
        break
    fi
done
if [[ "${migration_service_included}" != "true" ]]; then
    pull_services+=("${MIGRATION_SERVICE}")
fi

mkdir -p media model-cache/u2net

# 1. Login to GHCR
echo "🔑 Logging into GHCR..."
echo "$GHCR_PAT" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin

# 2. Pull only application images. PostgreSQL has a separate maintenance lifecycle.
echo "📥 Pulling application images: ${pull_services[*]}"
"${COMPOSE[@]}" pull "${pull_services[@]}"

# 3. Migrations
if [[ "${RUN_MIGRATIONS}" == "true" ]]; then
    echo "📦 Running database migrations..."
    "${COMPOSE[@]}" run -T --rm --no-deps "${MIGRATION_SERVICE}" alembic upgrade head
else
    echo "⏭️ Skipping database migrations (API_RUN_MIGRATIONS=${RUN_MIGRATIONS})"
fi

# 3.1 Ensure required global settings exist (idempotent).
if [[ "${RUN_DEFAULTS}" == "true" ]]; then
    echo "⚙️ Ensuring default global settings..."
    "${COMPOSE[@]}" run -T --rm --no-deps "${MIGRATION_SERVICE}" python3 scripts/ensure_global_config_defaults.py
else
    echo "⏭️ Skipping default global settings (API_RUN_DEFAULTS=${RUN_DEFAULTS})"
fi

# Persist the candidate only after pre-deploy work succeeds. Keep the previous
# image reference for an immediate code rollback.
ENV_FILE="${PROJECT_DIR}/.env"
PREVIOUS_IMAGE_FILE="${PROJECT_DIR}/.previous-backend-image"
touch "${ENV_FILE}"
previous_image="$(sed -n 's/^BACKEND_IMAGE=//p' "${ENV_FILE}" | tail -n 1)"
if [[ -n "${previous_image}" && "${previous_image}" != "${BACKEND_IMAGE}" ]]; then
    printf '%s\n' "${previous_image}" > "${PREVIOUS_IMAGE_FILE}"
    chmod 600 "${PREVIOUS_IMAGE_FILE}"
    echo "↩️ Recorded previous backend image in ${PREVIOUS_IMAGE_FILE}"
fi

env_tmp="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"
grep -v '^BACKEND_IMAGE=' "${ENV_FILE}" > "${env_tmp}" || true
printf 'BACKEND_IMAGE=%s\n' "${BACKEND_IMAGE}" >> "${env_tmp}"
chmod --reference="${ENV_FILE}" "${env_tmp}" 2>/dev/null || chmod 600 "${env_tmp}"
chown --reference="${ENV_FILE}" "${env_tmp}" 2>/dev/null || true
mv "${env_tmp}" "${ENV_FILE}"
echo "💾 Persisted immutable backend image in ${ENV_FILE}"

# 4. Recreate only application services. Blue-green switching is introduced in
# the next phase; --no-deps already guarantees that DB is not recreated here.
echo "🔄 Recreating application services: ${deploy_services[*]}"
"${COMPOSE[@]}" up -d --no-deps --force-recreate "${deploy_services[@]}"

echo "✅ Deployment completed successfully!"
