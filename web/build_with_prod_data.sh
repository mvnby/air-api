#!/bin/bash
# Helper script to build web frontend locally using production API data
# This ensures SSG fetches real data, not localhost test data

echo "🔨 Building web frontend with production data..."
echo "📡 API Source: https://api.mvn.by/api/v1"
echo ""

cd "$(dirname "$0")"

# Override API URLs to use production for SSG build
INTERNAL_API_URL="https://api.mvn.by/api/v1" \
PUBLIC_API_URL="https://api.mvn.by/api/v1" \
PUBLIC_SITE_URL="https://mvn.by" \
npm run build

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Build complete! Ready to deploy with: ./deploy_web.sh [dev|prod]"
else
    echo ""
    echo "❌ Build failed"
    exit 1
fi
