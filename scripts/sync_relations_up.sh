#!/bin/bash
set -e

# Configuration
REMOTE_HOST="${REMOTE_HOST:-root@185.250.45.54}"
REMOTE_USER="mvnadmin" 
REMOTE_DB="air_conditioners"
LOCAL_CONTAINER="mvn-db-1"
LOCAL_USER="mvnadmin"
LOCAL_DB="air_conditioners"

echo "========================================"
echo "📤 Syncing RELATIONS tables UP to $REMOTE_HOST..."
echo "========================================"

# Tables to sync
TABLES="tag product_tag_link product_image"

echo "💾 Dumping local tables: $TABLES..."
docker exec $LOCAL_CONTAINER pg_dump -U $LOCAL_USER -d $LOCAL_DB --data-only $(printf -- "--table=%s " $TABLES) --column-inserts > relations_dump.sql

if [ ! -s relations_dump.sql ]; then
    echo "❌ Dump failed or empty!"
    exit 1
fi

echo "✅ Dump created: relations_dump.sql"

# Upload
echo "🚀 Uploading dump to $REMOTE_HOST..."
scp relations_dump.sql $REMOTE_HOST:/tmp/relations_dump.sql

# Restore
echo "♻️ Restoring on remote (Truncate + Insert)..."
# Copy to container
ssh $REMOTE_HOST "docker cp /tmp/relations_dump.sql air-api-db-1:/tmp/relations_dump.sql"
# Execute (Truncate first)
TRUNCATE_CMD="TRUNCATE TABLE product_tag_link, product_image, tag CASCADE;"
ssh $REMOTE_HOST "docker exec air-api-db-1 psql -U $REMOTE_USER -d $REMOTE_DB -c '$TRUNCATE_CMD' && docker exec air-api-db-1 psql -U $REMOTE_USER -d $REMOTE_DB -f /tmp/relations_dump.sql"

# Cleanup
echo "🧹 Cleaning up..."
rm relations_dump.sql
ssh $REMOTE_HOST "rm /tmp/relations_dump.sql"

echo "✅ Relations synced successfully!"
