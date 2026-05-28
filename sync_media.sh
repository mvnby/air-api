#!/bin/bash

# Syncs local media files to the remote server
# Usage: ./sync_media.sh

REMOTE_HOST="${REMOTE_HOST:-root@185.250.45.54}"
REMOTE_DIR="/opt/air-api/media"
LOCAL_DIR="./media/"

echo "Syncing media files to $REMOTE_HOST:$REMOTE_DIR ..."

# -a: archive mode (preserves permissions, times, symbolic links)
# -v: verbose
# -z: compress during transfer
# --progress: show progress during transfer
rsync -avz --progress "$LOCAL_DIR" "$REMOTE_HOST:$REMOTE_DIR"

echo "✅ Sync complete."
