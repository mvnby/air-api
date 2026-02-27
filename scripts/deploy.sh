#!/bin/bash
set -e
set -o pipefail

echo "🚀 Starting deployment script on server..."

cd /opt/air-api

# 1. Login to GHCR
echo "🔑 Logging into GHCR..."
echo "$GHCR_PAT" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin

# 2. Pull images
echo "📥 Pulling latest Docker images..."
docker compose -f docker-compose.prod.yml pull

# 3. Migrations
echo "📦 Running database migrations..."
# Use -T to avoid TTY issues
docker compose -f docker-compose.prod.yml run -T --rm app alembic upgrade head

# 3.1 Ensure required global settings exist (idempotent).
echo "⚙️ Ensuring default global settings..."
docker compose -f docker-compose.prod.yml run -T --rm app python3 scripts/ensure_global_config_defaults.py

# 4. Stop old containers
echo "🛑 Stopping old containers..."
docker compose -f docker-compose.prod.yml stop app bot || true

# 5. Start new containers
echo "🔄 Starting services..."
docker compose -f docker-compose.prod.yml up -d --force-recreate app bot

# 6. Cleanup
echo "🧹 Cleaning up unused Docker objects (images, containers, networks)..."
docker system prune -af

echo "✅ Deployment completed successfully!"
