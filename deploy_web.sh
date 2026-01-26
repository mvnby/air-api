#!/bin/bash
set -e

# Configuration
WEB_HOST="mvn-web"
API_HOST="mvn-api"
# User specified path for SSG
REMOTE_WEB_DIR="/var/www/user2154318/data/www/dev.mvn.by"
LOCAL_WEB_DIR="./web"
export PUBLIC_SITE_URL="https://dev.mvn.by"

echo "========================================"
echo "🚀 Deploying WEB (SSG) to $WEB_HOST..."
echo "========================================"

# 1. Sync media from API (for build/static assets)
echo "🖼️ Syncing media files from $API_HOST..."
# Ensure local media dir exists
mkdir -p "$LOCAL_WEB_DIR/public/media"
rsync -avz "$API_HOST:/opt/air-api/media/" "$LOCAL_WEB_DIR/public/media/"

# 2. Build Frontend Locally
echo "📦 Building Astro project..."
cd "$LOCAL_WEB_DIR"

# Set API URL for the build process (SSG needs access to API)
# We use the public API URL because we are building locally (outside docker network)
export INTERNAL_API_URL="https://api.mvn.by/api/v1"
export PUBLIC_API_URL="https://api.mvn.by/api/v1"
# Переменная теперь доступна для Astro во время npm run build
export PUBLIC_SITE_URL=$PUBLIC_SITE_URL

npm install
npm run build

if [ $? -ne 0 ]; then
    echo "❌ Build failed! Aborting."
    exit 1
fi
cd ..

# 3. Deploy Static Files
echo "📡 Uploading to $WEB_HOST:$REMOTE_WEB_DIR..."
# Ensure remote directory exists
ssh "$WEB_HOST" "mkdir -p $REMOTE_WEB_DIR"
# Sync dist contents to remote public_html
rsync -avz --delete "$LOCAL_WEB_DIR/dist/" "$WEB_HOST:$REMOTE_WEB_DIR/"
# 4. Активация robots.txt для разработки
echo "🤖 Setting up robots.txt for DEV environment..."
ssh "$WEB_HOST" "cp $REMOTE_WEB_DIR/robots.dev.txt $REMOTE_WEB_DIR/robots.txt"

echo "✅ WEB Deployment Complete!"
