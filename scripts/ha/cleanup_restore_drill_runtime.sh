#!/usr/bin/env bash
set -Eeuo pipefail

PITR_OPERATION_ID="${PITR_OPERATION_ID:-}"
DRILL_ROOT="${DRILL_ROOT:-}"
EXPECTED_DRILL_ROOT="/var/lib/mvn-postgres-pitr/logical-restore-drills"

log() {
  printf '[restore-drill] %s\n' "$*"
}

(( EUID == 0 )) || { echo "logical restore cleanup requires root" >&2; exit 2; }
[[ "${PITR_OPERATION_ID}" =~ ^[0-9a-f]{32}$ ]] || {
  echo "PITR_OPERATION_ID must be a guarded operation ID" >&2
  exit 2
}
[[ "${DRILL_ROOT}" == "${EXPECTED_DRILL_ROOT}" ]] || {
  echo "DRILL_ROOT is not the reviewed logical restore state root" >&2
  exit 2
}

RUN_ID="${PITR_OPERATION_ID}"
CONTAINER="mvn-logical-restore-${RUN_ID}"
DRILL_DIR="${DRILL_ROOT}/${RUN_ID}"

inspect_object() {
  local name="$1"
  local output=""
  local output_lower=""

  output="$(docker inspect "${name}" 2>&1)" && return 0
  output_lower="$(printf '%s' "${output}" | LC_ALL=C tr '[:upper:]' '[:lower:]')"
  case "${output_lower}" in
    *"no such object"* | *"no such container"*) return 1 ;;
    *) log "cleanup_error=container_inspect_failed name=${name}"; return 2 ;;
  esac
}

labels_match() {
  local name="$1"
  local labels=""

  labels="$(docker inspect --format '{{ index .Config.Labels "com.mvn.purpose" }}|{{ index .Config.Labels "com.mvn.pitr.operation" }}' "${name}" 2>/dev/null)" || return 1
  [[ "${labels}" == "api-restore-drill|${RUN_ID}" ]]
}

cleanup_failed=false
if inspect_object "${CONTAINER}"; then
  if ! labels_match "${CONTAINER}"; then
    log "cleanup_error=container_label_mismatch container=${CONTAINER}"
    cleanup_failed=true
  elif ! docker rm -fv "${CONTAINER}" >/dev/null 2>&1; then
    log "cleanup_error=container_remove_failed container=${CONTAINER}"
    cleanup_failed=true
  fi
elif [[ "$?" -eq 2 ]]; then
  cleanup_failed=true
fi

if inspect_object "${CONTAINER}"; then
  log "cleanup_error=container_still_exists container=${CONTAINER}"
  cleanup_failed=true
elif [[ "$?" -eq 2 ]]; then
  cleanup_failed=true
fi
if [[ -e "${DRILL_DIR}" || -L "${DRILL_DIR}" ]]; then
  metadata="$(stat -Lc '%u:%g:%a:%h' "${DRILL_DIR}" 2>/dev/null || true)"
  if [[ -L "${DRILL_DIR}" || ! -d "${DRILL_DIR}" || ! "${metadata}" =~ ^0:0:700:[2-9][0-9]*$ ]]; then
    log "cleanup_error=drill_directory_unsafe directory=${DRILL_DIR}"
    cleanup_failed=true
  else
    unexpected="$(
      find "${DRILL_DIR}" -mindepth 1 -maxdepth 1 \
        ! -name latest.sql ! -name latest.sql.gz ! -name restore.sql ! -name restore.log \
        ! -name restore.normalized.sql ! -name container.env \
        -print -quit
    )"
    if [[ -n "${unexpected}" ]]; then
      log "cleanup_error=unexpected_drill_artifact path=${unexpected}"
      cleanup_failed=true
    elif ! rm -f -- \
      "${DRILL_DIR}/latest.sql" \
      "${DRILL_DIR}/latest.sql.gz" \
      "${DRILL_DIR}/restore.sql" \
      "${DRILL_DIR}/restore.normalized.sql" \
      "${DRILL_DIR}/restore.log" \
      "${DRILL_DIR}/container.env"; then
      log "cleanup_error=drill_files_remove_failed"
      cleanup_failed=true
    elif ! rmdir -- "${DRILL_DIR}"; then
      log "cleanup_error=drill_directory_remove_failed directory=${DRILL_DIR}"
      cleanup_failed=true
    fi
  fi
fi

[[ "${cleanup_failed}" == "false" ]]
