#!/usr/bin/env bash
set -Eeuo pipefail

WEB_ROOT="${WEB_ROOT:-/var/www/mvn.by}"
RELEASE_ID="${WEB_RELEASE_ID:-}"
KEEP_RELEASES="${WEB_KEEP_RELEASES:-5}"
WEB_HOST="${WEB_HOST:-mvn.by}"
LIVE_LINK="${WEB_LIVE_LINK:-${WEB_ROOT}/live}"
RELEASES_DIR="${WEB_ROOT}/releases"
INCOMING_DIR="${RELEASES_DIR}/.${RELEASE_ID}.incoming"
RELEASE_DIR="${RELEASES_DIR}/${RELEASE_ID}"
LOCK_FILE="${WEB_DEPLOY_LOCK_FILE:-${WEB_ROOT}/.deploy.lock}"
SUMMARY_FILE="${WEB_DEPLOY_SUMMARY_FILE:-/tmp/web_deploy_summary.txt}"

previous_target=""
promoted=false

log() {
  printf '[web-promote][%s] %s\n' "$1" "$2"
}

atomic_link() {
  local target="$1"
  local next="${LIVE_LINK}.next.$$"
  ln -s "${target}" "${next}"
  python3 - "${next}" "${LIVE_LINK}" <<'PY'
import os
import sys

os.replace(sys.argv[1], sys.argv[2])
PY
}

rollback_on_error() {
  local exit_code=$?
  trap - ERR
  set +e
  if [[ "${promoted}" == "true" && -n "${previous_target}" ]]; then
    atomic_link "${previous_target}"
    log rollback "restored ${previous_target}"
  fi
  exit "${exit_code}"
}

[[ "${RELEASE_ID}" =~ ^[0-9a-f]{7,64}$ ]] || {
  log error "WEB_RELEASE_ID must be a 7-64 character lowercase hex commit id"
  exit 1
}
[[ "${KEEP_RELEASES}" =~ ^[1-9][0-9]*$ ]] || {
  log error "WEB_KEEP_RELEASES must be a positive integer"
  exit 1
}
[[ "${WEB_ROOT}" == /* && "${WEB_ROOT}" != "/" && "${WEB_ROOT}" != *".."* ]] || {
  log error "WEB_ROOT must be a safe absolute path"
  exit 1
}
for command in flock curl python3; do
  command -v "${command}" >/dev/null 2>&1 || {
    log error "required command is missing: ${command}"
    exit 1
  }
done
[[ -L "${LIVE_LINK}" ]] || {
  log error "atomic live symlink is missing: ${LIVE_LINK}"
  exit 1
}
[[ -d "${INCOMING_DIR}" ]] || {
  log error "incoming release is missing: ${INCOMING_DIR}"
  exit 1
}
[[ -s "${INCOMING_DIR}/index.html" ]] || {
  log error "incoming release has no index.html"
  exit 1
}
[[ -s "${INCOMING_DIR}/catalog/index.html" ]] || {
  log error "incoming release has no catalog/index.html"
  exit 1
}
python3 - "${INCOMING_DIR}/release.json" "${RELEASE_ID}" <<'PY'
import json
import sys
from pathlib import Path

release = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if release != {"sha": sys.argv[2]}:
    raise SystemExit("incoming release.json does not match WEB_RELEASE_ID")
PY

exec 9>"${LOCK_FILE}"
flock -n 9 || {
  log error "another web deployment holds ${LOCK_FILE}"
  exit 1
}
: > "${SUMMARY_FILE}"
trap rollback_on_error ERR

previous_target="$(readlink "${LIVE_LINK}")"
if [[ -d "${RELEASE_DIR}" ]]; then
  rm -rf "${INCOMING_DIR}"
else
  mv "${INCOMING_DIR}" "${RELEASE_DIR}"
fi
printf '%s\n' "${RELEASE_ID}" > "${RELEASE_DIR}/.release-id"

atomic_link "${RELEASE_DIR}"
promoted=true
curl -fsS --resolve "${WEB_HOST}:443:127.0.0.1" "https://${WEB_HOST}/" >/dev/null
curl -fsS --resolve "${WEB_HOST}:443:127.0.0.1" "https://${WEB_HOST}/catalog/" >/dev/null

active_target="$(readlink -f "${LIVE_LINK}")"
if ! python3 - "${RELEASES_DIR}" "${active_target}" "${KEEP_RELEASES}" <<'PY'
import re
import shutil
import sys
from pathlib import Path

releases = Path(sys.argv[1])
active = Path(sys.argv[2]).resolve()
keep = int(sys.argv[3])
candidates = [
    path
    for path in releases.iterdir()
    if path.is_dir() and re.fullmatch(r"[0-9a-f]{7,64}", path.name)
]
candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
for path in candidates[keep:]:
    if path.resolve() != active:
        shutil.rmtree(path)
PY
then
  log warning "old release cleanup failed; active release is unchanged"
fi

trap - ERR
{
  echo "status=activated"
  echo "release_id=${RELEASE_ID}"
  echo "release_dir=${RELEASE_DIR}"
  echo "previous_target=${previous_target}"
  echo "active_target=${active_target}"
} >> "${SUMMARY_FILE}"
log "done" "activated ${RELEASE_ID}"
