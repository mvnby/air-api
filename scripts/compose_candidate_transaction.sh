#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="${1:-}"
CANONICAL_FILE="${CANONICAL_COMPOSE_FILE:-}"
CANDIDATE_FILE="${CANDIDATE_COMPOSE_FILE:-}"
LEGACY_BACKUP_FILE="${LEGACY_COMPOSE_BACKUP_FILE:-${CANONICAL_FILE}.pre-google-oauth-dir}"

log() {
  printf '[compose-candidate][%s] %s\n' "$1" "$2"
}

fail() {
  log error "$1" >&2
  exit 1
}

fsync_path() {
  python3 - "$1" <<'PY'
import os
import sys

descriptor = os.open(sys.argv[1], os.O_RDONLY)
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
}

atomic_copy() {
  local source="$1"
  local destination="$2"
  local temporary
  temporary="$(mktemp "${destination}.tmp.XXXXXX")"
  if ! cp -p -- "${source}" "${temporary}"; then
    rm -f -- "${temporary}"
    return 1
  fi
  fsync_path "${temporary}" || {
    rm -f -- "${temporary}"
    return 1
  }
  if ! mv -f -- "${temporary}" "${destination}"; then
    rm -f -- "${temporary}"
    return 1
  fi
  fsync_path "$(dirname "${destination}")"
}

[[ "${ACTION}" == "stage" || "${ACTION}" == "promote" || "${ACTION}" == "cleanup" ]] || {
  echo "usage: compose_candidate_transaction.sh stage|promote|cleanup" >&2
  exit 2
}
[[ -n "${CANONICAL_FILE}" && -n "${CANDIDATE_FILE}" ]] || {
  fail "CANONICAL_COMPOSE_FILE and CANDIDATE_COMPOSE_FILE are required"
}
[[ "${CANONICAL_FILE}" != "${CANDIDATE_FILE}" ]] || {
  fail "candidate compose must differ from canonical compose"
}
[[ "$(dirname "${CANONICAL_FILE}")" == "$(dirname "${CANDIDATE_FILE}")" ]] || {
  fail "candidate and canonical compose must share a directory for atomic promotion"
}

case "${ACTION}" in
  stage)
    [[ -f "${CANONICAL_FILE}" && ! -L "${CANONICAL_FILE}" ]] || {
      fail "canonical compose is missing or unsafe: ${CANONICAL_FILE}"
    }
    [[ -f "${CANDIDATE_FILE}" && ! -L "${CANDIDATE_FILE}" ]] || {
      fail "candidate compose is missing or unsafe: ${CANDIDATE_FILE}"
    }
    if grep -Fq '/app/token.json' "${CANONICAL_FILE}"; then
      if [[ -e "${LEGACY_BACKUP_FILE}" || -L "${LEGACY_BACKUP_FILE}" ]]; then
        [[ -f "${LEGACY_BACKUP_FILE}" && ! -L "${LEGACY_BACKUP_FILE}" ]] || {
          fail "legacy compose backup is unsafe: ${LEGACY_BACKUP_FILE}"
        }
        cmp -s "${CANONICAL_FILE}" "${LEGACY_BACKUP_FILE}" || {
          fail "legacy compose backup differs from canonical; refusing a stale emergency artifact"
        }
      else
        atomic_copy "${CANONICAL_FILE}" "${LEGACY_BACKUP_FILE}"
      fi
    fi
    log stage "candidate staged; canonical compose remains unchanged"
    ;;
  promote)
    [[ -f "${CANDIDATE_FILE}" && ! -L "${CANDIDATE_FILE}" ]] || {
      fail "candidate compose is missing or unsafe: ${CANDIDATE_FILE}"
    }
    fsync_path "${CANDIDATE_FILE}"
    mv -f -- "${CANDIDATE_FILE}" "${CANONICAL_FILE}"
    fsync_path "$(dirname "${CANONICAL_FILE}")"
    ;;
  cleanup)
    rm -f -- "${CANDIDATE_FILE}"
    log cleanup "candidate removed"
    ;;
esac
