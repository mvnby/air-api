#!/usr/bin/env bash
set -euo pipefail

LOCK="${LOCK:-/run/mvn-media-sync.lock}"
SOURCE_HOST="${SOURCE_HOST:-root@10.77.0.2}"
SOURCE_DIR="${SOURCE_DIR:-/opt/air-api/media/}"
DEST_DIR="${DEST_DIR:-/opt/mvn-reserve/media/}"
SSH_KEY="${SSH_KEY:-/root/.ssh/mvn_media_sync_ed25519}"

SSH_OPTS=(
  ssh
  -i "${SSH_KEY}"
  -o BatchMode=yes
  -o ConnectTimeout=10
  -o StrictHostKeyChecking=accept-new
)

mkdir -p "${DEST_DIR}"
exec flock -n "${LOCK}" rsync -a --delete --delay-updates --numeric-ids -e "${SSH_OPTS[*]}" "${SOURCE_HOST}:${SOURCE_DIR}" "${DEST_DIR}"
