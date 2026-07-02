#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
APP_SERVICE="${APP_SERVICE:-app}"
ARCHIVE_DIR="${ARCHIVE_DIR:-/postgres-wal-archive}"
DRY_RUN_UPLOAD="${DRY_RUN_UPLOAD:-false}"
DELETE_AFTER_UPLOAD="${DELETE_AFTER_UPLOAD:-true}"

cd "${PROJECT_DIR}"
if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "Compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}" >&2
  exit 1
fi

upload_flags=()
if [[ "${DRY_RUN_UPLOAD}" == "true" ]]; then
  upload_flags+=(--dry-run)
fi
if [[ "${DELETE_AFTER_UPLOAD}" == "true" ]]; then
  upload_flags+=(--delete-after-upload)
else
  upload_flags+=(--no-delete-after-upload)
fi

docker compose -f "${COMPOSE_FILE}" run -T --rm "${APP_SERVICE}" \
  python scripts/ha/upload_postgres_pitr_to_s3.py wal \
    --archive-dir "${ARCHIVE_DIR}" \
    "${upload_flags[@]}"
