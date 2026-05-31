#!/bin/bash
set -e

# Usage: ./deploy_web.sh [dev|prod]
# Deploys the web frontend to either dev or production environment

# Configuration
ENVIRONMENT="${1:-dev}"  # Default to 'dev' if no argument provided
API_HOST="${API_HOST:-root@185.250.45.54}"
LOCAL_WEB_DIR="./web"

# Environment-specific configuration
if [ "$ENVIRONMENT" = "prod" ]; then
    WEB_HOST="mvn-web"
    REMOTE_WEB_DIR="/var/www/user2154318/data/www/mvn.by"
    PUBLIC_SITE_URL="https://mvn.by"
    PUBLIC_API_URL="https://api.mvn.by/api/v1"
    ROBOTS_TXT_SETUP="default"  # Production uses generated robots.txt
elif [ "$ENVIRONMENT" = "dev" ]; then
    WEB_HOST="mvn-web"
    REMOTE_WEB_DIR="/var/www/user2154318/data/www/dev.mvn.by"
    PUBLIC_SITE_URL="https://dev.mvn.by"
    PUBLIC_API_URL="https://api.mvn.by/api/v1"
    ROBOTS_TXT_SETUP="dev"
else
    echo "❌ ERROR: Invalid environment '$ENVIRONMENT'"
    echo "Usage: ./deploy_web.sh [dev|prod]"
    exit 1
fi

echo "========================================"
echo "🚀 Deploying WEB ($ENVIRONMENT) to $WEB_HOST..."
echo "Target: $REMOTE_WEB_DIR"
echo "URL: $PUBLIC_SITE_URL"
echo "API: $PUBLIC_API_URL"
echo "========================================"

# Pre-flight: Check if web is built
echo "🔍 Checking pre-built artifacts..."
if [ ! -d "$LOCAL_WEB_DIR/dist" ]; then
    echo "❌ ERROR: web/dist not found!"
    echo "📦 Building web frontend with production data..."
    echo ""
    
    # Build with production API URL to ensure SSG fetches real data
    cd "$LOCAL_WEB_DIR"
    
    # Force production API URL for data fetching during SSG build
    # This prevents local test data from polluting production
    echo "🔧 Using production API for data: https://api.mvn.by/api/v1"
    PUBLIC_API_URL="https://api.mvn.by/api/v1" \
    INTERNAL_API_URL="https://api.mvn.by/api/v1" \
    PUBLIC_SITE_URL="$PUBLIC_SITE_URL" \
    npm run build
    
    if [ $? -ne 0 ]; then
        echo "❌ Build failed! Aborting."
        exit 1
    fi
    
    cd - > /dev/null
fi
echo "✅ Web dist found"

# 1. Sync media from API (for build/static assets)
echo "🖼️ Syncing media files from $API_HOST..."
# Ensure local media dir exists
mkdir -p "$LOCAL_WEB_DIR/public/media"
rsync -avz "$API_HOST:/opt/air-api/media/" "$LOCAL_WEB_DIR/public/media/"

# 2. Deploy Static Files
echo "📡 Uploading to $WEB_HOST:$REMOTE_WEB_DIR..."
# Ensure remote directory exists
ssh "$WEB_HOST" "mkdir -p $REMOTE_WEB_DIR"
# Sync dist contents to remote public_html
rsync -avz --delete "$LOCAL_WEB_DIR/dist/" "$WEB_HOST:$REMOTE_WEB_DIR/"

# 3. Setup robots.txt based on environment
if [ "$ROBOTS_TXT_SETUP" = "dev" ]; then
    echo "🤖 Setting up robots.txt for DEV environment..."
    ssh "$WEB_HOST" "cp $REMOTE_WEB_DIR/robots.dev.txt $REMOTE_WEB_DIR/robots.txt"
else
    echo "🤖 Using default robots.txt for PRODUCTION"
fi

echo ""
echo "✅ WEB ($ENVIRONMENT) Deployment Complete!"
echo "   URL: $PUBLIC_SITE_URL"
