#!/bin/bash
set -e
set -o pipefail

echo "🚀 Starting deployment script on server..."

PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${API_COMPOSE_FILE:-docker-compose.prod.yml}"
DEPLOY_SERVICES="${API_DEPLOY_SERVICES:-app bot}"
MIGRATION_SERVICE="${API_MIGRATION_SERVICE:-app}"
RUN_MIGRATIONS="${API_RUN_MIGRATIONS:-true}"
RUN_DEFAULTS="${API_RUN_DEFAULTS:-true}"

if [[ ! -d "${PROJECT_DIR}" ]]; then
    echo "❌ Project dir not found: ${PROJECT_DIR}"
    exit 1
fi

cd "${PROJECT_DIR}"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
    echo "❌ Compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}"
    exit 1
fi

COMPOSE=(docker compose -f "${COMPOSE_FILE}")

mkdir -p media model-cache/u2net

# 1. Login to GHCR
echo "🔑 Logging into GHCR..."
echo "$GHCR_PAT" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin

# 2. Pull images
echo "📥 Pulling latest Docker images..."
"${COMPOSE[@]}" pull

# 3. Migrations
if [[ "${RUN_MIGRATIONS}" == "true" ]]; then
    echo "📦 Running database migrations..."
    # Use -T to avoid TTY issues
    "${COMPOSE[@]}" run -T --rm "${MIGRATION_SERVICE}" alembic upgrade head
else
    echo "⏭️ Skipping database migrations (API_RUN_MIGRATIONS=${RUN_MIGRATIONS})"
fi

# 3.1 Ensure required global settings exist (idempotent).
if [[ "${RUN_DEFAULTS}" == "true" ]]; then
    echo "⚙️ Ensuring default global settings..."
    "${COMPOSE[@]}" run -T --rm "${MIGRATION_SERVICE}" python3 scripts/ensure_global_config_defaults.py
else
    echo "⏭️ Skipping default global settings (API_RUN_DEFAULTS=${RUN_DEFAULTS})"
fi

# 4. Stop old containers
echo "🛑 Stopping old containers..."
"${COMPOSE[@]}" stop ${DEPLOY_SERVICES} || true

# 5. Start new containers
echo "🔄 Starting services..."
"${COMPOSE[@]}" up -d --force-recreate ${DEPLOY_SERVICES}

# 6. Cleanup
echo "🧹 Cleaning up unused Docker objects (images, containers, networks)..."
docker system prune -af

echo "✅ Deployment completed successfully!"
