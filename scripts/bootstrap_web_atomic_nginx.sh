#!/usr/bin/env bash
set -Eeuo pipefail

WEB_ROOT="${WEB_ROOT:-/var/www/mvn.by}"
LEGACY_DIR="${WEB_LEGACY_DIR:-${WEB_ROOT}/current}"
LIVE_LINK="${WEB_LIVE_LINK:-${WEB_ROOT}/live}"
NGINX_SITE_FILE="${WEB_NGINX_SITE_FILE:-/etc/nginx/sites-available/mvn.by}"
WEB_HOST="${WEB_HOST:-mvn.by}"
CONFIRM="${CONFIRM_WEB_NGINX_BOOTSTRAP:-false}"

created_live_link=false
site_changed=false
backup=""

log() {
  printf '[web-nginx][%s] %s\n' "$1" "$2"
}

rollback_on_error() {
  local exit_code=$?
  trap - ERR
  set +e
  if [[ "${site_changed}" == "true" && -n "${backup}" ]]; then
    cp -a "${backup}" "${NGINX_SITE_FILE}"
    nginx -t && systemctl reload nginx
  fi
  if [[ "${created_live_link}" == "true" ]]; then
    rm -f "${LIVE_LINK}"
  fi
  exit "${exit_code}"
}

if [[ "${CONFIRM}" != "true" ]]; then
  log error "set CONFIRM_WEB_NGINX_BOOTSTRAP=true to apply"
  exit 1
fi
for command in nginx systemctl python3 curl; do
  command -v "${command}" >/dev/null 2>&1 || {
    log error "required command is missing: ${command}"
    exit 1
  }
done
[[ -d "${LEGACY_DIR}" ]] || {
  log error "legacy web directory is missing: ${LEGACY_DIR}"
  exit 1
}
[[ -f "${NGINX_SITE_FILE}" ]] || {
  log error "nginx site is missing: ${NGINX_SITE_FILE}"
  exit 1
}

trap rollback_on_error ERR
if [[ -e "${LIVE_LINK}" && ! -L "${LIVE_LINK}" ]]; then
  log error "refusing to replace non-symlink ${LIVE_LINK}"
  exit 1
fi
if [[ ! -L "${LIVE_LINK}" ]]; then
  ln -s "${LEGACY_DIR}" "${LIVE_LINK}"
  created_live_link=true
fi
[[ -f "${LIVE_LINK}/index.html" ]] || {
  log error "live link does not resolve to a storefront index"
  exit 1
}

legacy_root="root ${LEGACY_DIR};"
live_root="root ${LIVE_LINK};"
if grep -Fq "${legacy_root}" "${NGINX_SITE_FILE}"; then
  backup="${NGINX_SITE_FILE}.pre-atomic-web-$(date -u +%Y%m%dT%H%M%SZ)"
  cp -a "${NGINX_SITE_FILE}" "${backup}"
  python3 - "${NGINX_SITE_FILE}" "${legacy_root}" "${live_root}" <<'PY'
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
old = sys.argv[2]
new = sys.argv[3]
text = path.read_text(encoding="utf-8")
if old not in text:
    raise SystemExit(f"legacy nginx root not found in {path}")
updated = text.replace(old, new)
tmp = path.with_name(f"{path.name}.tmp")
tmp.write_text(updated, encoding="utf-8")
os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
os.replace(tmp, path)
PY
  site_changed=true
elif ! grep -Fq "${live_root}" "${NGINX_SITE_FILE}"; then
  log error "nginx site contains neither legacy nor managed live root"
  exit 1
fi

nginx -t
if [[ "${site_changed}" == "true" ]]; then
  systemctl reload nginx
fi
curl -fsS --resolve "${WEB_HOST}:443:127.0.0.1" "https://${WEB_HOST}/" >/dev/null

trap - ERR
log "done" "nginx serves ${LIVE_LINK}; current content is unchanged"
