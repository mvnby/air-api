#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-}"
COMPOSE_FILE="${COMPOSE_FILE:-}"
APP_SERVICE="${APP_SERVICE:-app}"
ARCHIVE_DIR=""
DRY_RUN_UPLOAD="${DRY_RUN_UPLOAD:-false}"
DELETE_AFTER_UPLOAD="${DELETE_AFTER_UPLOAD:-true}"
RUNTIME_CHECK_HELPER="${RUNTIME_CHECK_HELPER:-/usr/local/sbin/mvn-postgres-pitr-runtime-check}"
TOOL_RUNNER="/usr/local/sbin/mvn-postgres-pitr-tool-runner"

export DOCKER_CONTEXT="${DOCKER_CONTEXT:-default}"

[[ -n "${PROJECT_DIR}" ]] || { echo "PROJECT_DIR must be set" >&2; exit 1; }
[[ "${COMPOSE_FILE}" == "docker-compose.patroni.yml" ]] || {
  echo "COMPOSE_FILE must be docker-compose.patroni.yml" >&2
  exit 1
}
[[ "${DOCKER_CONTEXT:-}" == "default" ]] || {
  echo "DOCKER_CONTEXT must be default" >&2
  exit 1
}
cd "${PROJECT_DIR}"
if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "Compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}" >&2
  exit 1
fi

BACKEND_IMAGE="$(
  "${RUNTIME_CHECK_HELPER}" \
    --project-dir "${PROJECT_DIR}" \
    --compose-file "${COMPOSE_FILE}"
)"
export BACKEND_IMAGE
ARCHIVE_DIR="${PROJECT_DIR}/postgres-wal-archive"
[[ -x "${TOOL_RUNNER}" ]] || { echo "PITR tool runner is unavailable" >&2; exit 1; }

upload_flags=()
if [[ "${DRY_RUN_UPLOAD}" == "true" ]]; then
  upload_flags+=(--dry-run)
fi
if [[ "${DELETE_AFTER_UPLOAD}" == "true" ]]; then
  upload_flags+=(--delete-after-upload)
else
  upload_flags+=(--no-delete-after-upload)
fi

"${TOOL_RUNNER}" \
  --phase wal-upload \
  --data-dir "${ARCHIVE_DIR}" \
  "${upload_flags[@]}"
