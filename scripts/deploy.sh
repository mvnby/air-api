#!/bin/bash
set -e
set -o pipefail

# Define variables
USER_API="root"
HOST_API="89.39.120.97"
# Note: Secrets are passed as environment variables or arguments. 
# We'll use environment variables set by the GitHub Action.

echo "🚀 Starting deployment script on server..."

cd /opt/air-api

# 1. Login to GHCR
echo "🔑 Logging into GHCR..."
# Pass standard input from the variable
echo "$GHCR_PAT" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin

# 2. Pull images
echo "📥 Pulling latest Docker images..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull

# 3. Migrations
echo "📦 Running database migrations..."
# Use -T to avoid TTY issues
docker compose -f docker-compose.yml -f docker-compose.prod.yml run -T --rm app alembic upgrade head

# 4. Stop old containers
echo "🛑 Stopping old containers..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop app bot || true

# 5. Start new containers
echo "🔄 Starting services..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate app bot

# 6. Cleanup
echo "🧹 Cleaning up old images..."
docker image prune -f

echo "✅ Deployment completed successfully!"
