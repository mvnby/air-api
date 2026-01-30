#!/bin/bash
set -e

# Configuration
# Assuming remote settings match sync_db.sh or similar patterns
REMOTE_HOST="mvn-api"
REMOTE_USER="mvnadmin"   # Adjust if needed, usually same as local dev default or from env on server 
REMOTE_DB="air_conditioners"
LOCAL_CONTAINER="mvn-db-1"
LOCAL_USER="mvnadmin"
LOCAL_DB="air_conditioners"
TABLE_NAME="product"

echo "========================================"
echo "📤 Syncing 'products' table UP to $REMOTE_HOST..."
echo "========================================"

# 1. Dump local table (Data Only to avoid schema conflicts, assuming schema is same)
echo "💾 Dumping local '$TABLE_NAME' table..."
docker exec $LOCAL_CONTAINER pg_dump -U $LOCAL_USER -d $LOCAL_DB --data-only --table=$TABLE_NAME --column-inserts > products_dump.sql

if [ ! -s products_dump.sql ]; then
    echo "❌ Dump failed or empty!"
    exit 1
fi

echo "✅ Dump created: products_dump.sql"

# 2. Upload dump to remote
echo "🚀 Uploading dump to $REMOTE_HOST..."
scp products_dump.sql $REMOTE_HOST:/tmp/products_dump.sql

# 3. Restore on remote
# WARNING: We are truncating the remote table to avoid conflicts!
echo "♻️ Restoring on remote (Truncate + Insert)..."

# Copy into container
ssh $REMOTE_HOST "docker cp /tmp/products_dump.sql air-api-db-1:/tmp/products_dump.sql"

# Execute
ssh $REMOTE_HOST "docker exec air-api-db-1 psql -U $REMOTE_USER -d $REMOTE_DB -c 'TRUNCATE TABLE $TABLE_NAME CASCADE;' && docker exec air-api-db-1 psql -U $REMOTE_USER -d $REMOTE_DB -f /tmp/products_dump.sql"

# 4. Cleanup
echo "🧹 Cleaning up..."
rm products_dump.sql
ssh $REMOTE_HOST "rm /tmp/products_dump.sql"

echo "✅ Products table synced successfully!"
