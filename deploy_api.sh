#!/bin/bash
set -e

# Configuration
REMOTE_HOST="mvn-api"
REMOTE_DIR="/opt/air-api"
DOCKER_COMPOSE_FILE="docker-compose.api.yml"

echo "========================================"
echo "🚀 Deploying API to $REMOTE_HOST..."
echo "========================================"

# 1. Sync files
echo "📂 Syncing files..."
rsync -avz --delete \
    --exclude 'web/' \
    --exclude 'web' \
    --exclude '__pycache__' \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude 'node_modules' \
    --exclude 'media' \
    --exclude 'tmp' \
    ./ "$REMOTE_HOST:$REMOTE_DIR"
# 2. Update Google tokens on remote
echo "🔑 Обновление токенов Google на API сервере..."
# Отправляем локальный token.json на сервер в папку проекта
# Замени /path/to/project на реальный путь, где лежит docker-compose.yml на сервере
rsync -avz ./token.json $REMOTE_HOST:$REMOTE_DIR/token.json
# 3. Deploy on remote
echo "🐳 Restarting containers on remote..."
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && \
    docker compose -f $DOCKER_COMPOSE_FILE pull && \
    docker compose -f $DOCKER_COMPOSE_FILE up -d --build --remove-orphans && \
    docker system prune -f"

echo "✅ API Deployment Complete!"
