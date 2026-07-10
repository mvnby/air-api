#!/usr/bin/env bash
set -euo pipefail

BACKEND_IMAGE_REPOSITORY="${BACKEND_IMAGE_REPOSITORY:-ghcr.io/mvnby/air-api/backend}"
KEEP_BACKEND_IMAGES="${KEEP_BACKEND_IMAGES:-3}"
PRUNE_DANGLING_UNTIL="${PRUNE_DANGLING_UNTIL:-168h}"

if ! [[ "${KEEP_BACKEND_IMAGES}" =~ ^[1-9][0-9]*$ ]]; then
  echo "KEEP_BACKEND_IMAGES must be a positive integer" >&2
  exit 2
fi

echo "== Disk usage before scoped Docker image prune =="
df -h /
docker system df || true

echo "== Keeping ${KEEP_BACKEND_IMAGES} newest backend images and all running images =="
index=0
while IFS= read -r image_id; do
  [[ -z "${image_id}" ]] && continue
  if (( index < KEEP_BACKEND_IMAGES )); then
    echo "keep newest backend image: ${image_id}"
    index=$((index + 1))
    continue
  fi
  if [[ -n "$(docker ps -aq --filter "ancestor=${image_id}")" ]]; then
    echo "keep running backend image: ${image_id}"
    index=$((index + 1))
    continue
  fi
  echo "remove old backend image: ${image_id}"
  docker image rm "${image_id}"
  index=$((index + 1))
done < <(
  docker image ls --no-trunc --digests --format '{{.Repository}} {{.ID}}' \
    | awk -v repository="${BACKEND_IMAGE_REPOSITORY}" \
      '$1 == repository && !seen[$2]++ { print $2 }'
)

echo "== Pruning only dangling images older than ${PRUNE_DANGLING_UNTIL} =="
docker image prune -f --filter "until=${PRUNE_DANGLING_UNTIL}"

echo "== Disk usage after scoped Docker image prune =="
docker system df || true
df -h /
