#!/bin/bash
set -e

# Configuration
REMOTE_HOST="mvn-api"
REMOTE_DIR="/opt/air-api"
DOCKER_COMPOSE_FILE="docker-compose.api.yml"

echo "========================================"
echo "🚀 Deploying API to $REMOTE_HOST..."
echo "========================================"

# 1. Sync files (code + alembic migrations)
echo "📂 Syncing files..."
rsync -avz --delete \
    --exclude 'web/' \
    --exclude 'web' \
    --exclude '__pycache__' \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude 'node_modules' \
    --exclude 'media' \
    --exclude 'backups' \
    --exclude 'tmp' \
    --exclude '.env' \
    --exclude 'env.prod' \
    ./ "$REMOTE_HOST:$REMOTE_DIR"

# 1.5. Deploy production environment file
echo "⚙️  Setting up production environment..."
rsync -avz ./env.prod "$REMOTE_HOST:$REMOTE_DIR/.env"

# 2. Update Google tokens on remote
echo "🔑 Syncing Google tokens..."
rsync -avz ./token.json "$REMOTE_HOST:$REMOTE_DIR/token.json" 2>/dev/null || echo "⚠️  No token.json found, skipping..."

# 3. Build new images on remote
echo "🐳 Building containers..."
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && \
    docker compose -f $DOCKER_COMPOSE_FILE build --no-cache app bot"

# 4. Run database migrations BEFORE restarting
echo "📦 Running database migrations..."
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && \
    docker compose -f $DOCKER_COMPOSE_FILE run --rm app alembic upgrade head"

# 5. Restart services with new images
echo "🔄 Restarting services..."
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && \
    docker compose -f $DOCKER_COMPOSE_FILE up -d --remove-orphans && \
    docker system prune -f"

# 6. Verify deployment
echo "🔍 Checking logs..."
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && docker compose logs app --tail=10"

echo ""
echo "✅ API Deployment Complete!"
echo "   Admin: https://api.mvn.by/admin/"
echo "   Health: https://api.mvn.by/api/health"
