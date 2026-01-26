#!/bin/bash
set -e

REMOTE_HOST="mvn-api"
REMOTE_DIR="/opt/air-api"
BACKUP_DIR="backups"

echo "========================================"
echo "📥 Syncing Production Database from $REMOTE_HOST..."
echo "========================================"

# 1. List remote backups and find the latest one
echo "🔍 Searching for latest backup on remote..."
LATEST_BACKUP=$(ssh "$REMOTE_HOST" "ls -t $REMOTE_DIR/$BACKUP_DIR/*.sql | head -n 1")

if [ -z "$LATEST_BACKUP" ]; then
    echo "❌ No backup found on remote!"
    exit 1
fi

BACKUP_FILENAME=$(basename "$LATEST_BACKUP")
echo "✅ Found latest backup: $BACKUP_FILENAME"

# 2. Download backup
echo "⬇️ Downloading backup..."
mkdir -p "$BACKUP_DIR"
rsync -avz "$REMOTE_HOST:$LATEST_BACKUP" "$BACKUP_DIR/$BACKUP_FILENAME"

# 3. Restore to local Docker
echo "♻️ Restoring to local Docker container..."

# Check if container is running
if [ "$(docker inspect -f '{{.State.Running}}' mvn-db-1 2>/dev/null)" != "true" ]; then
    echo "⚠️ Database container is not running. Starting it..."
    docker compose up -d db
    echo "⏳ Waiting for database to be ready..."
    sleep 5
fi

# Determine container user and db name (defaults from .env analysis)
DB_USER="mvnadmin"
DB_NAME="air_conditioners"

# Copy dump into container (optional, but robust)
docker cp "$BACKUP_DIR/$BACKUP_FILENAME" mvn-db-1:/tmp/restore.sql

# Restore
# Note: We use psql to restore. Assuming the dump is plain SQL.
echo "🔄 Executing restore..."
docker exec mvn-db-1 psql -U "$DB_USER" -d "$DB_NAME" -f /tmp/restore.sql > /dev/null

# Clean up inside container
docker exec mvn-db-1 rm /tmp/restore.sql

echo "✅ Database synced successfully!"
echo "📂 Local dump saved at: $BACKUP_DIR/$BACKUP_FILENAME"
