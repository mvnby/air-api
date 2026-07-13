#!/usr/bin/env bash
set -Eeuo pipefail

CONTAINER="${RESTORE_DRILL_CONTAINER:-}"
DATA_VOLUME="${RESTORE_DRILL_DATA_VOLUME:-}"
RUN_ID="${RESTORE_DRILL_RUN_ID:-}"
DRILL_DIR="${RESTORE_DRILL_DIR:-/tmp/mvn-restore-drill}"
KEEP_CONTAINER="${KEEP_DRILL_CONTAINER:-false}"
KEEP_FILES="${KEEP_DRILL_FILES:-false}"

log() {
  printf '[restore-drill] %s\n' "$*"
}

inspect_object() {
  local kind="$1"
  local name="$2"
  local output=""
  local output_lower=""

  if [[ "${kind}" == "container" ]]; then
    output="$(docker inspect "${name}" 2>&1)" && return 0
  else
    output="$(docker volume inspect "${name}" 2>&1)" && return 0
  fi
  # Docker CLI/daemon versions disagree on the capitalization of not-found
  # errors (for example, `No such container` vs `no such object`). Normalize
  # only for the known absence signatures; every other inspect failure remains
  # fail-closed.
  output_lower="$(printf '%s' "${output}" | LC_ALL=C tr '[:upper:]' '[:lower:]')"
  case "${output_lower}" in
    *"no such object"*|*"no such container"*|*"no such volume"*) return 1 ;;
    *) log "cleanup_error=${kind}_inspect_failed name=${name}"; return 2 ;;
  esac
}

labels_match() {
  local kind="$1"
  local name="$2"
  local labels=""

  if [[ "${kind}" == "container" ]]; then
    labels="$(docker inspect --format '{{ index .Config.Labels "com.mvn.purpose" }}|{{ index .Config.Labels "com.mvn.run_id" }}' "${name}" 2>/dev/null)" \
      || return 1
  else
    labels="$(docker volume inspect --format '{{ index .Labels "com.mvn.purpose" }}|{{ index .Labels "com.mvn.run_id" }}' "${name}" 2>/dev/null)" \
      || return 1
  fi
  [[ "${labels}" == "api-restore-drill|${RUN_ID}" ]]
}

[[ -n "${CONTAINER}" && -n "${DATA_VOLUME}" && -n "${RUN_ID}" ]] || {
  echo "RESTORE_DRILL_CONTAINER, RESTORE_DRILL_DATA_VOLUME, and RESTORE_DRILL_RUN_ID are required" >&2
  exit 2
}
[[ "${KEEP_CONTAINER}" == "true" || "${KEEP_CONTAINER}" == "false" ]] || exit 2
[[ "${KEEP_FILES}" == "true" || "${KEEP_FILES}" == "false" ]] || exit 2

cleanup_failed=false
if [[ "${KEEP_CONTAINER}" != "true" ]]; then
  if inspect_object container "${CONTAINER}"; then
    if ! labels_match container "${CONTAINER}"; then
      log "cleanup_error=container_label_mismatch container=${CONTAINER}"
      cleanup_failed=true
    elif ! docker rm -fv "${CONTAINER}" >/dev/null 2>&1; then
      log "cleanup_error=container_remove_failed container=${CONTAINER}"
      cleanup_failed=true
    fi
  elif [[ "$?" -eq 2 ]]; then
    cleanup_failed=true
  fi
  if inspect_object volume "${DATA_VOLUME}"; then
    if ! labels_match volume "${DATA_VOLUME}"; then
      log "cleanup_error=volume_label_mismatch volume=${DATA_VOLUME}"
      cleanup_failed=true
    elif ! docker volume rm "${DATA_VOLUME}" >/dev/null 2>&1; then
      log "cleanup_error=volume_remove_failed volume=${DATA_VOLUME}"
      cleanup_failed=true
    fi
  elif [[ "$?" -eq 2 ]]; then
    cleanup_failed=true
  fi
  if inspect_object container "${CONTAINER}"; then
    log "cleanup_error=container_still_exists container=${CONTAINER}"
    cleanup_failed=true
  elif [[ "$?" -eq 2 ]]; then
    cleanup_failed=true
  fi
  if inspect_object volume "${DATA_VOLUME}"; then
    log "cleanup_error=volume_still_exists volume=${DATA_VOLUME}"
    cleanup_failed=true
  elif [[ "$?" -eq 2 ]]; then
    cleanup_failed=true
  fi
else
  log "cleanup_skipped=true container=${CONTAINER} volume=${DATA_VOLUME}"
fi

if [[ "${KEEP_FILES}" != "true" ]]; then
  if ! rm -f \
    "${DRILL_DIR}/latest-db-backup.sql" \
    "${DRILL_DIR}/latest-db-backup.sql.gz" \
    "${DRILL_DIR}/restore.log"; then
    log "cleanup_error=drill_files_remove_failed"
    cleanup_failed=true
  fi
  if [[ -d "${DRILL_DIR}" ]] && ! rmdir "${DRILL_DIR}"; then
    log "cleanup_error=drill_directory_remove_failed directory=${DRILL_DIR}"
    cleanup_failed=true
  fi
fi

[[ "${cleanup_failed}" == "false" ]]
