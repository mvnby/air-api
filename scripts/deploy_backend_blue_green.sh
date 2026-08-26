#!/usr/bin/env bash
# shellcheck disable=SC2034
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${API_COMPOSE_FILE:-docker-compose.prod.yml}"
BACKEND_IMAGE="${BACKEND_IMAGE:-}"
REQUESTED_IMAGE="${BACKEND_IMAGE}"
RUN_MIGRATIONS="${API_RUN_MIGRATIONS:-true}"
RUN_DEFAULTS="${API_RUN_DEFAULTS:-true}"
BOOTSTRAP_ONLY="${API_BLUE_GREEN_BOOTSTRAP_ONLY:-false}"
FORCE_ACTIVATION="${API_FORCE_ACTIVATION:-false}"
DEPLOY_LOCK_FILE="${API_DEPLOY_LOCK_FILE:-${PROJECT_DIR}/.deploy.lock}"
DEPLOY_LOCK_FD="${API_DEPLOY_LOCK_FD:-}"
DEPLOY_LOCK_HELPER="${API_DEPLOY_LOCK_HELPER:-${SCRIPT_DIR}/ha/safe_deploy_lock.py}"
DEPLOY_LOCK_HELPER_SHA256="${API_DEPLOY_LOCK_HELPER_SHA256:-}"
CAPACITY_HELPER="${API_DEPLOY_CAPACITY_HELPER:-${SCRIPT_DIR}/ha/require_deploy_capacity.sh}"
SAFETY_HELPER="${API_BLUE_GREEN_SAFETY_HELPER:-${SCRIPT_DIR}/deploy_backend_blue_green_safety.sh}"
PITR_MAINTENANCE_MARKER="/run/mvn-postgres-pitr-maintenance"
PITR_MARKER_VALIDATOR="${API_PITR_MAINTENANCE_MARKER_VALIDATOR:-${SCRIPT_DIR}/ha/verify_pitr_maintenance_marker.py}"
ACTIVE_SLOT_FILE="${API_ACTIVE_SLOT_FILE:-${PROJECT_DIR}/.active-api-slot}"
PREVIOUS_IMAGE_FILE="${PROJECT_DIR}/.previous-backend-image"
ENV_FILE="${PROJECT_DIR}/.env"
BLUE_PORT="${API_BLUE_PORT:-18001}"
GREEN_PORT="${API_GREEN_PORT:-18002}"
LEGACY_PORT="${API_LEGACY_PORT:-8000}"
NGINX_SITE_FILE="${API_NGINX_SITE_FILE:-/etc/nginx/sites-available/air-api}"
NGINX_UPSTREAM_FILE="${API_NGINX_UPSTREAM_FILE:-/etc/nginx/snippets/mvn-api-upstream.conf}"
NGINX_INTERNAL_FILE="${API_NGINX_INTERNAL_FILE:-/etc/nginx/conf.d/mvn-api-internal.conf}"
PROXY_MODE="${API_PROXY_MODE:-host_nginx}"
PROXY_SERVICE="${API_PROXY_SERVICE:-api-proxy}"
PROXY_CONFIG_FILE="${API_PROXY_CONFIG_FILE:-${PROJECT_DIR}/api-proxy/nginx.conf}"
INTERNAL_PROXY_PORT="${API_INTERNAL_PROXY_PORT:-18080}"
API_HOST="${API_HOST:-api.mvn.by}"
PUBLIC_READY_URL="${API_PUBLIC_READY_URL:-https://${API_HOST}/api/ready}"
HEALTH_ATTEMPTS="${API_HEALTH_ATTEMPTS:-45}"
HEALTH_DELAY_SECONDS="${API_HEALTH_DELAY_SECONDS:-2}"
SCHEDULER_READY_ATTEMPTS="${API_SCHEDULER_READY_ATTEMPTS:-${HEALTH_ATTEMPTS}}"
SCHEDULER_STABILITY_SECONDS="${API_SCHEDULER_STABILITY_SECONDS:-9}"
SERVICE_STOP_TIMEOUT_SECONDS="${API_SERVICE_STOP_TIMEOUT_SECONDS:-5}"
DRAIN_SECONDS="${API_DRAIN_SECONDS:-5}"
SUMMARY_FILE="${API_BLUE_GREEN_SUMMARY_FILE:-/tmp/backend_blue_green_summary.txt}"
GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT="${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT:-${SCRIPT_DIR}/prepare_google_oauth_token_dir.sh}"
DOCUMENT_PDF_SERVICE="${DOCUMENT_PDF_SERVICE:-gotenberg}"
DOCUMENT_PDF_WAIT_TIMEOUT="${DOCUMENT_PDF_WAIT_TIMEOUT:-90}"

active_slot="legacy"
active_service="app"
active_port="${LEGACY_PORT}"
candidate_slot=""
candidate_service=""
candidate_port=""
previous_image=""
env_updated=false
nginx_switch_attempted=false
candidate_started=false
old_service_stop_started=false
TMP_DIR=""

log() {
  printf '[blue-green][%s] %s\n' "$1" "$2"
}

ensure_document_pdf_runtime() {
  log document-pdf "pulling and waiting for private ${DOCUMENT_PDF_SERVICE} runtime"
  "${COMPOSE[@]}" pull "${DOCUMENT_PDF_SERVICE}"
  require_deploy_capacity
  "${COMPOSE[@]}" up -d --no-deps --wait --wait-timeout \
    "${DOCUMENT_PDF_WAIT_TIMEOUT}" "${DOCUMENT_PDF_SERVICE}"
  log document-pdf "private ${DOCUMENT_PDF_SERVICE} runtime is healthy"
}
if [[ "${API_DEPLOY_LOCK_ALREADY_HELD:-false}" == "true" && -z "${DEPLOY_LOCK_FD}" ]]; then
  log error "legacy deploy-lock boolean cannot replace an inherited descriptor"
  exit 1
fi

summary() {
  printf '%s\n' "$1" >> "${SUMMARY_FILE}"
}
is_immutable_image() {
  [[ "$1" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]]
}

slot_for_port() {
  case "$1" in
    "${BLUE_PORT}") printf 'blue\n' ;;
    "${GREEN_PORT}") printf 'green\n' ;;
    "${LEGACY_PORT}") printf 'legacy\n' ;;
    *) return 1 ;;
  esac
}

service_for_slot() {
  case "$1" in
    blue|green) printf 'app-%s\n' "$1" ;;
    legacy) printf 'app\n' ;;
    *) return 1 ;;
  esac
}

port_for_slot() {
  case "$1" in
    blue) printf '%s\n' "${BLUE_PORT}" ;;
    green) printf '%s\n' "${GREEN_PORT}" ;;
    legacy) printf '%s\n' "${LEGACY_PORT}" ;;
    *) return 1 ;;
  esac
}

atomic_write_line() {
  local path="$1"
  local value="$2"
  local fallback_mode="${3:-600}"
  local tmp

  mkdir -p "$(dirname "${path}")"
  tmp="$(mktemp "${path}.tmp.XXXXXX")"
  printf '%s\n' "${value}" > "${tmp}"
  chmod --reference="${path}" "${tmp}" 2>/dev/null || chmod "${fallback_mode}" "${tmp}"
  chown --reference="${path}" "${tmp}" 2>/dev/null || true
  mv "${tmp}" "${path}"
}

write_backend_image() {
  local image="$1"
  local tmp

  touch "${ENV_FILE}"
  tmp="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"
  grep -v '^BACKEND_IMAGE=' "${ENV_FILE}" > "${tmp}" || true
  printf 'BACKEND_IMAGE=%s\n' "${image}" >> "${tmp}"
  chmod --reference="${ENV_FILE}" "${tmp}" 2>/dev/null || chmod 600 "${tmp}"
  chown --reference="${ENV_FILE}" "${tmp}" 2>/dev/null || true
  mv "${tmp}" "${ENV_FILE}"
}

upstream_target_for_slot() {
  local slot="$1"

  case "${PROXY_MODE}" in
    host_nginx)
      printf '127.0.0.1:%s\n' "$(port_for_slot "${slot}")"
      ;;
    container_nginx)
      printf '%s:8000\n' "$(service_for_slot "${slot}")"
      ;;
    *)
      log error "unsupported API_PROXY_MODE=${PROXY_MODE}"
      return 1
      ;;
  esac
}

write_upstream() {
  local slot="$1"
  local target
  target="$(upstream_target_for_slot "${slot}")"
  atomic_write_line "${NGINX_UPSTREAM_FILE}" "proxy_pass http://${target};" 644
}

parse_upstream_slot() {
  local target
  target="$(
    sed -nE 's/^[[:space:]]*proxy_pass[[:space:]]+http:\/\/([^;]+);[[:space:]]*$/\1/p' \
      "${NGINX_UPSTREAM_FILE}" | tail -n 1
  )"

  case "${PROXY_MODE}" in
    host_nginx)
      [[ "${target}" =~ ^127\.0\.0\.1:([0-9]+)$ ]] || return 1
      slot_for_port "${BASH_REMATCH[1]}"
      ;;
    container_nginx)
      case "${target}" in
        app:8000) printf 'legacy\n' ;;
        app-blue:8000) printf 'blue\n' ;;
        app-green:8000) printf 'green\n' ;;
        *) return 1 ;;
      esac
      ;;
    *) return 1 ;;
  esac
}

resolve_active_slot() {
  local include_line="include ${NGINX_UPSTREAM_FILE};"
  local configured_slot=""

  case "${PROXY_MODE}" in
    host_nginx)
      if grep -Fq "${include_line}" "${NGINX_SITE_FILE}"; then
        [[ -f "${NGINX_UPSTREAM_FILE}" ]] || {
          log error "managed nginx include exists but ${NGINX_UPSTREAM_FILE} is missing"
          return 1
        }
        active_slot="$(parse_upstream_slot)" || {
          log error "cannot parse active slot from ${NGINX_UPSTREAM_FILE}"
          return 1
        }
      else
        active_slot="legacy"
      fi
      ;;
    container_nginx)
      if [[ -f "${NGINX_UPSTREAM_FILE}" ]]; then
        active_slot="$(parse_upstream_slot)" || {
          log error "cannot parse active slot from ${NGINX_UPSTREAM_FILE}"
          return 1
        }
      else
        active_slot="legacy"
      fi
      ;;
    *)
      log error "unsupported API_PROXY_MODE=${PROXY_MODE}"
      return 1
      ;;
  esac

  if [[ -f "${ACTIVE_SLOT_FILE}" ]]; then
    configured_slot="$(tr -d '\r\n' < "${ACTIVE_SLOT_FILE}")"
    if [[ "${configured_slot}" != "blue" && "${configured_slot}" != "green" ]]; then
      log error "invalid active slot record: ${configured_slot}"
      return 1
    fi
    if [[ "${active_slot}" != "${configured_slot}" ]]; then
      log error "active slot record (${configured_slot}) disagrees with nginx (${active_slot})"
      return 1
    fi
  elif [[ "${active_slot}" != "legacy" ]]; then
    log error "nginx uses ${active_slot}, but ${ACTIVE_SLOT_FILE} is missing"
    return 1
  fi

  active_service="$(service_for_slot "${active_slot}")"
  active_port="$(port_for_slot "${active_slot}")"
}

ensure_managed_nginx_upstream() {
  local include_line="include ${NGINX_UPSTREAM_FILE};"
  local backup

  if grep -Fq "${include_line}" "${NGINX_SITE_FILE}"; then
    return 0
  fi

  write_upstream "${active_slot}"
  backup="${NGINX_SITE_FILE}.pre-blue-green-$(date -u +%Y%m%dT%H%M%SZ)"
  cp -a "${NGINX_SITE_FILE}" "${backup}"

  python3 - "${NGINX_SITE_FILE}" "${LEGACY_PORT}" "${include_line}" <<'PY'
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
legacy_port = sys.argv[2]
include_line = sys.argv[3]
text = path.read_text(encoding="utf-8")
needle = f"proxy_pass http://127.0.0.1:{legacy_port};"
if text.count(needle) != 1:
    raise SystemExit(f"expected exactly one legacy proxy_pass in {path}")
updated = text.replace(needle, include_line)
tmp = path.with_name(f"{path.name}.tmp")
tmp.write_text(updated, encoding="utf-8")
mode = stat.S_IMODE(path.stat().st_mode)
os.chmod(tmp, mode)
os.replace(tmp, path)
PY

  if ! nginx -t; then
    cp -a "${backup}" "${NGINX_SITE_FILE}"
    log error "nginx validation failed; restored ${backup}"
    return 1
  fi
  systemctl reload nginx
  log nginx "installed managed upstream include; legacy port remains active"
}

reload_proxy() {
  case "${PROXY_MODE}" in
    host_nginx)
      nginx -t
      systemctl reload nginx
      ;;
    container_nginx)
      "${COMPOSE[@]}" exec -T "${PROXY_SERVICE}" nginx -t
      "${COMPOSE[@]}" exec -T "${PROXY_SERVICE}" nginx -s reload
      ;;
    *)
      log error "unsupported API_PROXY_MODE=${PROXY_MODE}"
      return 1
      ;;
  esac
}

ensure_container_proxy() {
  [[ -f "${PROXY_CONFIG_FILE}" ]] || {
    log error "container proxy config is missing: ${PROXY_CONFIG_FILE}"
    return 1
  }
  if [[ ! -f "${NGINX_UPSTREAM_FILE}" ]]; then
    write_upstream "${active_slot}"
  fi
  "${COMPOSE[@]}" up -d --no-deps "${PROXY_SERVICE}"
  reload_proxy
  log nginx "container proxy ${PROXY_SERVICE} routes ${active_slot} through 127.0.0.1:${INTERNAL_PROXY_PORT}"
}

ensure_proxy() {
  case "${PROXY_MODE}" in
    host_nginx)
      ensure_managed_nginx_upstream
      ensure_internal_proxy
      ;;
    container_nginx)
      ensure_container_proxy
      ;;
    *)
      log error "unsupported API_PROXY_MODE=${PROXY_MODE}"
      return 1
      ;;
  esac
}

ensure_internal_proxy() {
  local marker="# Managed by deploy_backend_blue_green.sh"
  local tmp
  local backup=""

  if [[ -f "${NGINX_INTERNAL_FILE}" ]] && ! grep -Fq "${marker}" "${NGINX_INTERNAL_FILE}"; then
    log error "refusing to replace unmanaged nginx file ${NGINX_INTERNAL_FILE}"
    return 1
  fi

  mkdir -p "$(dirname "${NGINX_INTERNAL_FILE}")"
  tmp="$(mktemp "${NGINX_INTERNAL_FILE}.tmp.XXXXXX")"
  cat > "${tmp}" <<EOF
${marker}
server {
    listen 127.0.0.1:${INTERNAL_PROXY_PORT};
    server_name _;
    client_max_body_size 20M;

    location / {
        include ${NGINX_UPSTREAM_FILE};
        proxy_set_header Host ${API_HOST};
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 60s;
    }
}
EOF
  chmod 644 "${tmp}"

  if [[ -f "${NGINX_INTERNAL_FILE}" ]] && cmp -s "${tmp}" "${NGINX_INTERNAL_FILE}"; then
    rm -f "${tmp}"
    return 0
  fi
  if [[ -f "${NGINX_INTERNAL_FILE}" ]]; then
    backup="${NGINX_INTERNAL_FILE}.pre-blue-green-$(date -u +%Y%m%dT%H%M%SZ)"
    cp -a "${NGINX_INTERNAL_FILE}" "${backup}"
  fi
  mv "${tmp}" "${NGINX_INTERNAL_FILE}"

  if ! nginx -t; then
    if [[ -n "${backup}" ]]; then
      cp -a "${backup}" "${NGINX_INTERNAL_FILE}"
    else
      rm -f "${NGINX_INTERNAL_FILE}"
    fi
    log error "nginx validation failed while installing the internal API proxy"
    return 1
  fi
  systemctl reload nginx
  log nginx "internal API proxy listens on 127.0.0.1:${INTERNAL_PROXY_PORT}"
}

validate_ready_payload() {
  local path="$1"
  python3 - "${path}" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
if payload.get("status") != "ok" or payload.get("api") != "ready":
    raise SystemExit(f"readiness payload is not ready: {payload}")
if payload.get("database") != "online" or payload.get("database_writable") is not True:
    raise SystemExit(f"database is not writable: {payload}")
PY
}

wait_ready_url() {
  local label="$1"
  local url="$2"
  shift 2
  local output="${TMP_DIR}/${label//[^A-Za-z0-9]/_}.json"

  for attempt in $(seq 1 "${HEALTH_ATTEMPTS}"); do
    if curl -fsS "$@" "${url}" > "${output}" 2>/dev/null && validate_ready_payload "${output}"; then
      log smoke "${label} ready on attempt ${attempt}"
      return 0
    fi
    sleep "${HEALTH_DELAY_SECONDS}"
  done
  log error "${label} did not become ready: ${url}"
  return 1
}

validate_scheduler_running_payload() {
  local path="$1"
  python3 - "${path}" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
runtime = payload.get("scheduler_runtime")
if not isinstance(runtime, dict):
    raise SystemExit(f"scheduler runtime payload is missing: {payload}")
if runtime.get("expected") is not True or runtime.get("status") != "running":
    raise SystemExit(f"scheduler runtime is not active: {runtime}")
PY
}

wait_scheduler_running_url() {
  local label="$1"
  local url="$2"
  local output="${TMP_DIR}/${label//[^A-Za-z0-9]/_}.json"
  local consecutive=0
  local required_samples=6
  local stable_since_ns=""
  local current_ns=""

  for attempt in $(seq 1 "${SCHEDULER_READY_ATTEMPTS}"); do
    if curl -fsS "${url}" > "${output}" 2>/dev/null \
      && validate_ready_payload "${output}" \
      && validate_scheduler_running_payload "${output}"; then
      consecutive=$((consecutive + 1))
      current_ns="$(monotonic_now_ns)" || {
        log error "could not read the monotonic clock for ${label}"
        return 1
      }
      if (( consecutive == 1 )); then
        stable_since_ns="${current_ns}"
      fi
      if (( consecutive >= required_samples )) \
        && scheduler_stability_elapsed "${stable_since_ns}" "${current_ns}"; then
        log smoke "${label} running for ${consecutive} consecutive samples and at least ${SCHEDULER_STABILITY_SECONDS}s (attempt ${attempt})"
        return 0
      fi
    else
      consecutive=0
      stable_since_ns=""
    fi
    sleep "${HEALTH_DELAY_SECONDS}"
  done
  log error "${label} did not remain running for ${required_samples} consecutive samples and at least ${SCHEDULER_STABILITY_SECONDS}s: ${url}"
  return 1
}

smoke_candidate() {
  local base_url="$1"
  local health_file="${TMP_DIR}/candidate-health.json"
  local products_file="${TMP_DIR}/candidate-products.json"
  local filters_file="${TMP_DIR}/candidate-filters.json"

  wait_ready_url "candidate" "${base_url}/api/ready"
  curl -fsS "${base_url}/api/health" > "${health_file}"
  curl -fsS "${base_url}/api/v1/products?limit=5" > "${products_file}"
  curl -fsS "${base_url}/api/v1/filters/config" > "${filters_file}"
  python3 - "${health_file}" "${products_file}" "${filters_file}" <<'PY'
import json
import sys

health = json.load(open(sys.argv[1], encoding="utf-8"))
products = json.load(open(sys.argv[2], encoding="utf-8"))
filters = json.load(open(sys.argv[3], encoding="utf-8"))
if health.get("status") != "ok" or health.get("database") != "online":
    raise SystemExit(f"health check failed: {health}")
if not isinstance(products.get("items"), list):
    raise SystemExit("products payload missing items")
for key in ("price", "area", "brands", "expert_tags"):
    if key not in filters:
        raise SystemExit(f"filters payload missing {key}")
PY
  log smoke "candidate API contract checks passed"
}

if [[ -e "${PITR_MAINTENANCE_MARKER}" || -L "${PITR_MAINTENANCE_MARKER}" ]]; then
  python3 /usr/local/libexec/mvn-pitr/verify_pitr_maintenance_marker.py pre-source \
    "${API_PITR_MAINTENANCE_TRANSACTION_ID:-}" "$0" "${DEPLOY_LOCK_HELPER}" "${SAFETY_HELPER}" "${CAPACITY_HELPER}" || {
    log error "PITR maintenance requires the pinned attested internal scrub runtime"; exit 1;
  }
fi
# shellcheck disable=SC1090,SC1091
source "${SAFETY_HELPER}"
[[ -f "${CAPACITY_HELPER}" && ! -L "${CAPACITY_HELPER}" ]] || {
  log error "deploy capacity helper is missing or unsafe: ${CAPACITY_HELPER}"
  exit 1
}
# shellcheck disable=SC1090
source "${CAPACITY_HELPER}"

required_commands=(docker curl python3 awk)
if [[ "${PROXY_MODE}" == "host_nginx" ]]; then
  required_commands+=(nginx systemctl)
fi
for command in "${required_commands[@]}"; do
  command -v "${command}" >/dev/null 2>&1 || {
    log error "required command is missing: ${command}"
    exit 1
  }
done
docker compose version >/dev/null

[[ -n "${BACKEND_IMAGE}" ]] || {
  log error "BACKEND_IMAGE is required"
  exit 1
}
[[ "${SCHEDULER_STABILITY_SECONDS}" =~ ^[0-9]+([.][0-9]+)?$ ]] || {
  log error "API_SCHEDULER_STABILITY_SECONDS must be a non-negative number"
  exit 1
}
if [[ ! "${SERVICE_STOP_TIMEOUT_SECONDS}" =~ ^([1-9]|10)$ ]]; then
  log error "API_SERVICE_STOP_TIMEOUT_SECONDS must be an integer from 1 to 10"
  exit 1
fi
[[ "${DOCUMENT_PDF_SERVICE}" == "gotenberg" ]] || {
  log error "DOCUMENT_PDF_SERVICE must be gotenberg"
  exit 1
}
[[ "${DOCUMENT_PDF_WAIT_TIMEOUT}" =~ ^[1-9][0-9]*$ ]] \
  && (( DOCUMENT_PDF_WAIT_TIMEOUT <= 300 )) || {
  log error "DOCUMENT_PDF_WAIT_TIMEOUT must be an integer from 1 to 300"
  exit 1
}
is_immutable_image "${BACKEND_IMAGE}" || {
  log error "BACKEND_IMAGE must use a Git SHA tag or sha256 digest"
  exit 1
}
[[ -f "${PROJECT_DIR}/${COMPOSE_FILE}" ]] || {
  log error "compose file is missing: ${PROJECT_DIR}/${COMPOSE_FILE}"
  exit 1
}
if [[ "${PROXY_MODE}" == "host_nginx" ]]; then
  [[ -f "${NGINX_SITE_FILE}" ]] || {
    log error "nginx site is missing: ${NGINX_SITE_FILE}"
    exit 1
  }
elif [[ "${PROXY_MODE}" != "container_nginx" ]]; then
  log error "unsupported API_PROXY_MODE=${PROXY_MODE}"
  exit 1
fi

cd "${PROJECT_DIR}"
[[ "${DEPLOY_LOCK_HELPER_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
  log error "safe deployment lock helper digest is missing"; exit 1;
}
python3 - "${DEPLOY_LOCK_HELPER}" "${DEPLOY_LOCK_HELPER_SHA256}" <<'PY'
import hashlib, os, stat, sys
path, expected = sys.argv[1:]
before = os.lstat(path)
if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
        or before.st_uid != os.geteuid() or before.st_nlink != 1
        or before.st_mode & 0o022):
    raise SystemExit("safe deployment lock helper metadata is unsafe")
fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
try:
    opened = os.fstat(fd); data = b""
    while True:
        chunk = os.read(fd, 131072)
        if not chunk: break
        data += chunk
finally: os.close(fd)
if ((opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        or hashlib.sha256(data).hexdigest() != expected):
    raise SystemExit("safe deployment lock helper source is unreviewed")
PY
if [[ -z "${DEPLOY_LOCK_FD}" ]]; then
  exec python3 "${DEPLOY_LOCK_HELPER}" exec "${DEPLOY_LOCK_FILE}" bash "$0" "$@"
fi
[[ "${DEPLOY_LOCK_FD}" == "9" && "${DEPLOY_LOCK_HELPER_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
  log error "blue-green deploy requires the exact inherited deployment lock fd"; exit 1;
}
python3 "${DEPLOY_LOCK_HELPER}" verify "${DEPLOY_LOCK_FILE}" "${DEPLOY_LOCK_FD}"
require_pitr_maintenance_clear_or_attested_scrub
require_deploy_capacity

[[ -f "${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT}" ]] || {
  log error "Google OAuth token preparation script is missing: ${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT}"
  exit 1
}
GOOGLE_OAUTH_PROJECT_DIR="${PROJECT_DIR}" \
  bash "${GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT}" prepare

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT
: > "${SUMMARY_FILE}"
COMPOSE=(docker compose -f "${COMPOSE_FILE}" --profile bluegreen)

resolve_active_slot
configured_image="$(sed -n 's/^BACKEND_IMAGE=//p' "${ENV_FILE}" | tail -n 1)"
previous_image="$(inspect_service_runtime_image "${active_service}")" || {
  log error "active API runtime image could not be established"
  exit 1
}

if [[ "${BOOTSTRAP_ONLY}" == "true" ]]; then
  if [[ "${configured_image}" != "${previous_image}" ]]; then
    log error "BOOTSTRAP_ONLY refuses BACKEND_IMAGE drift: env=${configured_image:-missing} runtime=${previous_image}"
    exit 1
  fi
  ensure_proxy
  smoke_candidate "http://127.0.0.1:${active_port}"
  wait_ready_url "internal_proxy" "http://127.0.0.1:${INTERNAL_PROXY_PORT}/api/ready"
  summary "status=bootstrap_complete"
  summary "active_slot=${active_slot}"
  summary "active_port=${active_port}"
  summary "internal_proxy_port=${INTERNAL_PROXY_PORT}"
  log "done" "nginx blue-green prerequisites are ready; no containers changed"
  exit 0
fi

if [[ "${configured_image}" != "${previous_image}" ]]; then
  log reconcile "restoring BACKEND_IMAGE from active runtime ${previous_image}"
  write_backend_image "${previous_image}"
fi
mkdir -p media model-cache/u2net
ensure_proxy
ensure_document_pdf_runtime

if [[ "${active_slot}" != "legacy" \
  && "${BACKEND_IMAGE}" == "${previous_image}" \
  && "${FORCE_ACTIVATION}" != "true" \
  && ! -f "${PROJECT_DIR}/.rollback-api-buffer.compose.yml" ]]; then
  smoke_candidate "http://127.0.0.1:${active_port}"
  wait_ready_url "origin" "https://${API_HOST}/api/ready" --resolve "${API_HOST}:443:127.0.0.1"
  wait_ready_url "public" "${PUBLIC_READY_URL}"
  wait_scheduler_running_url \
    "active_scheduler" \
    "http://127.0.0.1:${active_port}/api/ready"
  summary "status=already_active"
  summary "active_slot=${active_slot}"
  summary "active_port=${active_port}"
  summary "backend_image=${BACKEND_IMAGE}"
  log "done" "requested image is already active"
  exit 0
fi

if [[ "${active_slot}" == "blue" ]]; then
  candidate_slot="green"
else
  candidate_slot="blue"
fi
candidate_service="$(service_for_slot "${candidate_slot}")"
candidate_port="$(port_for_slot "${candidate_slot}")"

trap rollback_on_error ERR
export BACKEND_IMAGE
if [[ -n "${GHCR_PAT:-}" ]]; then
  printf '%s' "${GHCR_PAT}" | docker login ghcr.io -u "${GITHUB_ACTOR:-github-actions}" --password-stdin
fi

log pull "pulling API candidate service ${candidate_service}"
"${COMPOSE[@]}" pull "${candidate_service}"
require_deploy_capacity

if [[ "${RUN_MIGRATIONS}" == "true" ]]; then
  "${COMPOSE[@]}" run -T --rm --no-deps "${candidate_service}" alembic upgrade head
fi
if [[ "${RUN_DEFAULTS}" == "true" ]]; then
  require_deploy_capacity
  "${COMPOSE[@]}" run -T --rm --no-deps "${candidate_service}" python3 scripts/ensure_global_config_defaults.py
fi

log start "starting ${candidate_service} on 127.0.0.1:${candidate_port}"
require_deploy_capacity
candidate_started=true
"${COMPOSE[@]}" up -d --no-deps --force-recreate "${candidate_service}"
smoke_candidate "http://127.0.0.1:${candidate_port}"

write_backend_image "${BACKEND_IMAGE}"
env_updated=true

nginx_switch_attempted=true
write_upstream "${candidate_slot}"
reload_proxy
log switch "nginx now routes to ${candidate_slot} on ${candidate_port}"

wait_ready_url "origin" "https://${API_HOST}/api/ready" --resolve "${API_HOST}:443:127.0.0.1"
wait_ready_url "public" "${PUBLIC_READY_URL}"
sleep "${DRAIN_SECONDS}"

old_service_stop_started=true
"${COMPOSE[@]}" stop -t "${SERVICE_STOP_TIMEOUT_SECONDS}" "${active_service}"
"${COMPOSE[@]}" rm -f "${active_service}"
atomic_write_line "${ACTIVE_SLOT_FILE}" "${candidate_slot}" 600
wait_scheduler_running_url \
  "candidate_scheduler" \
  "http://127.0.0.1:${candidate_port}/api/ready"
rm -f "${PROJECT_DIR}/.rollback-api-buffer.compose.yml"
atomic_write_line "${PREVIOUS_IMAGE_FILE}" "${previous_image}" 600

trap - ERR
summary "status=activated"
summary "previous_slot=${active_slot}"
summary "active_slot=${candidate_slot}"
summary "active_port=${candidate_port}"
summary "backend_image=${BACKEND_IMAGE}"
summary "previous_image=${previous_image}"
log "done" "activated ${candidate_slot}; previous service ${active_service} is stopped"
