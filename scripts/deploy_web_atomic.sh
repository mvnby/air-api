#!/usr/bin/env bash
set -euo pipefail

WEB_HOST="${WEB_HOST:-}"
WEB_SITE_HOST="${WEB_SITE_HOST:-mvn.by}"
WEB_USER="${WEB_USER:-deploy}"
WEB_ROOT="${WEB_ROOT:-/var/www/mvn.by}"
WEB_RELEASE_ID="${WEB_RELEASE_ID:-}"
WEB_DIST_DIR="${WEB_DIST_DIR:-web/dist}"
SSH_KEY_PATH="${SSH_KEY_PATH:-${HOME}/.ssh/deploy_key}"
KEEP_RELEASES="${WEB_KEEP_RELEASES:-5}"
MAX_ATTEMPTS="${WEB_DEPLOY_MAX_ATTEMPTS:-3}"
REMOTE_HELPER="${WEB_REMOTE_HELPER:-/tmp/promote_web_release.sh}"
PROMOTE_HELPER_SOURCE="${WEB_PROMOTE_HELPER_SOURCE:-scripts/promote_web_release.sh}"

log() {
  printf '[web-deploy][%s] %s\n' "$1" "$2"
}

quote() {
  printf '%q' "$1"
}

[[ -n "${WEB_HOST}" ]] || {
  log error "WEB_HOST is required"
  exit 1
}
[[ "${WEB_ROOT}" == /* && "${WEB_ROOT}" != "/" && "${WEB_ROOT}" != *".."* ]] || {
  log error "WEB_ROOT must be a safe absolute path"
  exit 1
}
[[ "${WEB_RELEASE_ID}" =~ ^[0-9a-f]{7,64}$ ]] || {
  log error "WEB_RELEASE_ID must be a lowercase hex commit id"
  exit 1
}
[[ -s "${WEB_DIST_DIR}/index.html" ]] || {
  log error "built storefront is missing: ${WEB_DIST_DIR}/index.html"
  exit 1
}
[[ -s "${WEB_DIST_DIR}/catalog/index.html" ]] || {
  log error "built catalog is missing: ${WEB_DIST_DIR}/catalog/index.html"
  exit 1
}
python3 - "${WEB_DIST_DIR}/release.json" "${WEB_RELEASE_ID}" <<'PY'
import json
import sys
from pathlib import Path

release = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if release != {"sha": sys.argv[2]}:
    raise SystemExit("release.json does not match WEB_RELEASE_ID")
PY
[[ -f "${PROMOTE_HELPER_SOURCE}" ]] || {
  log error "promotion helper is missing: ${PROMOTE_HELPER_SOURCE}"
  exit 1
}
for command in ssh rsync; do
  command -v "${command}" >/dev/null 2>&1 || {
    log error "required command is missing: ${command}"
    exit 1
  }
done

SSH_OPTS=(
  -i "${SSH_KEY_PATH}"
  -o BatchMode=yes
  -o StrictHostKeyChecking=yes
  -o ConnectTimeout=15
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=3
)
target="${WEB_USER}@${WEB_HOST}"
incoming="${WEB_ROOT}/releases/.${WEB_RELEASE_ID}.incoming"

prepared=false
for attempt in $(seq 1 "${MAX_ATTEMPTS}"); do
  log prepare "attempt ${attempt}/${MAX_ATTEMPTS}"
  # shellcheck disable=SC2029
  if ssh "${SSH_OPTS[@]}" "${target}" \
    "mkdir -p $(quote "${WEB_ROOT}/releases") && rm -rf $(quote "${incoming}") && mkdir -p $(quote "${incoming}")" \
    && cat "${PROMOTE_HELPER_SOURCE}" | ssh "${SSH_OPTS[@]}" "${target}" \
      "cat > $(quote "${REMOTE_HELPER}") && chmod 0755 $(quote "${REMOTE_HELPER}")"; then
    prepared=true
    break
  fi
  sleep $((attempt * 10))
done
[[ "${prepared}" == "true" ]] || {
  log error "remote release preparation failed after ${MAX_ATTEMPTS} attempts"
  exit 1
}

uploaded=false
for attempt in $(seq 1 "${MAX_ATTEMPTS}"); do
  log upload "attempt ${attempt}/${MAX_ATTEMPTS}"
  if rsync -az --delete --delay-updates \
    -e "ssh ${SSH_OPTS[*]}" \
    "${WEB_DIST_DIR}/" \
    "${target}:${incoming}/"; then
    uploaded=true
    break
  fi
  sleep $((attempt * 10))
done
[[ "${uploaded}" == "true" ]] || {
  log error "rsync failed after ${MAX_ATTEMPTS} attempts"
  exit 1
}

# shellcheck disable=SC2029
ssh "${SSH_OPTS[@]}" "${target}" "\
  WEB_ROOT=$(quote "${WEB_ROOT}") \
  WEB_RELEASE_ID=$(quote "${WEB_RELEASE_ID}") \
  WEB_KEEP_RELEASES=$(quote "${KEEP_RELEASES}") \
  WEB_HOST=$(quote "${WEB_SITE_HOST}") \
  WEB_DEPLOY_SUMMARY_FILE=/tmp/web_deploy_summary.txt \
  bash $(quote "${REMOTE_HELPER}") && \
  cat /tmp/web_deploy_summary.txt"
log "done" "atomic VPS release ${WEB_RELEASE_ID} is active"
