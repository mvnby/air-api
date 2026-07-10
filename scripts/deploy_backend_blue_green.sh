#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
COMPOSE_FILE="${API_COMPOSE_FILE:-docker-compose.prod.yml}"
BACKEND_IMAGE="${BACKEND_IMAGE:-}"
REQUESTED_IMAGE="${BACKEND_IMAGE}"
RUN_MIGRATIONS="${API_RUN_MIGRATIONS:-true}"
RUN_DEFAULTS="${API_RUN_DEFAULTS:-true}"
BOOTSTRAP_ONLY="${API_BLUE_GREEN_BOOTSTRAP_ONLY:-false}"
DEPLOY_LOCK_FILE="${API_DEPLOY_LOCK_FILE:-${PROJECT_DIR}/.deploy.lock}"
DEPLOY_LOCK_ALREADY_HELD="${API_DEPLOY_LOCK_ALREADY_HELD:-false}"
ACTIVE_SLOT_FILE="${API_ACTIVE_SLOT_FILE:-${PROJECT_DIR}/.active-api-slot}"
PREVIOUS_IMAGE_FILE="${PROJECT_DIR}/.previous-backend-image"
ENV_FILE="${PROJECT_DIR}/.env"
BLUE_PORT="${API_BLUE_PORT:-18001}"
GREEN_PORT="${API_GREEN_PORT:-18002}"
LEGACY_PORT="${API_LEGACY_PORT:-8000}"
NGINX_SITE_FILE="${API_NGINX_SITE_FILE:-/etc/nginx/sites-available/air-api}"
NGINX_UPSTREAM_FILE="${API_NGINX_UPSTREAM_FILE:-/etc/nginx/snippets/mvn-api-upstream.conf}"
NGINX_INTERNAL_FILE="${API_NGINX_INTERNAL_FILE:-/etc/nginx/conf.d/mvn-api-internal.conf}"
INTERNAL_PROXY_PORT="${API_INTERNAL_PROXY_PORT:-18080}"
API_HOST="${API_HOST:-api.mvn.by}"
PUBLIC_READY_URL="${API_PUBLIC_READY_URL:-https://${API_HOST}/api/ready}"
HEALTH_ATTEMPTS="${API_HEALTH_ATTEMPTS:-45}"
HEALTH_DELAY_SECONDS="${API_HEALTH_DELAY_SECONDS:-2}"
DRAIN_SECONDS="${API_DRAIN_SECONDS:-5}"
SUMMARY_FILE="${API_BLUE_GREEN_SUMMARY_FILE:-/tmp/backend_blue_green_summary.txt}"

active_slot="legacy"
active_service="app"
active_port="${LEGACY_PORT}"
candidate_slot=""
candidate_service=""
candidate_port=""
previous_image=""
env_updated=false
bot_update_attempted=false
nginx_switch_attempted=false
candidate_started=false
old_service_stopped=false
TMP_DIR=""

log() {
  printf '[blue-green][%s] %s\n' "$1" "$2"
}

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

write_upstream() {
  local port="$1"
  atomic_write_line "${NGINX_UPSTREAM_FILE}" "proxy_pass http://127.0.0.1:${port};" 644
}

parse_upstream_port() {
  sed -nE 's/^[[:space:]]*proxy_pass[[:space:]]+http:\/\/127\.0\.0\.1:([0-9]+);[[:space:]]*$/\1/p' \
    "${NGINX_UPSTREAM_FILE}" | tail -n 1
}

resolve_active_slot() {
  local include_line="include ${NGINX_UPSTREAM_FILE};"
  local configured_slot=""
  local upstream_port=""

  if grep -Fq "${include_line}" "${NGINX_SITE_FILE}"; then
    [[ -f "${NGINX_UPSTREAM_FILE}" ]] || {
      log error "managed nginx include exists but ${NGINX_UPSTREAM_FILE} is missing"
      return 1
    }
    upstream_port="$(parse_upstream_port)"
    [[ -n "${upstream_port}" ]] || {
      log error "cannot parse active port from ${NGINX_UPSTREAM_FILE}"
      return 1
    }
    active_slot="$(slot_for_port "${upstream_port}")" || {
      log error "nginx points to unmanaged API port ${upstream_port}"
      return 1
    }
  else
    active_slot="legacy"
  fi

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

  write_upstream "${active_port}"
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

wait_service_running() {
  local service="$1"
  local running

  for _ in $(seq 1 15); do
    running="$("${COMPOSE[@]}" ps --status running --services 2>/dev/null || true)"
    if grep -Fxq "${service}" <<<"${running}"; then
      return 0
    fi
    sleep 1
  done
  log error "compose service is not running: ${service}"
  return 1
}

rollback_on_error() {
  local exit_code=$?
  trap - ERR
  set +e
  log rollback "activation failed; restoring ${active_slot} on port ${active_port}"

  if [[ "${env_updated}" == "true" ]] && is_immutable_image "${previous_image}"; then
    export BACKEND_IMAGE="${previous_image}"
    write_backend_image "${previous_image}"
  fi
  if [[ "${old_service_stopped}" == "true" ]] && is_immutable_image "${previous_image}"; then
    export BACKEND_IMAGE="${previous_image}"
    "${COMPOSE[@]}" up -d --no-deps "${active_service}"
  fi

  if [[ "${nginx_switch_attempted}" == "true" && -f "${NGINX_UPSTREAM_FILE}" ]]; then
    write_upstream "${active_port}"
    nginx -t && systemctl reload nginx
  fi

  if [[ "${bot_update_attempted}" == "true" ]] && is_immutable_image "${previous_image}"; then
    export BACKEND_IMAGE="${previous_image}"
    "${COMPOSE[@]}" up -d --no-deps --force-recreate bot
  fi
  if [[ "${candidate_started}" == "true" && -n "${candidate_service}" ]]; then
    "${COMPOSE[@]}" stop "${candidate_service}"
    "${COMPOSE[@]}" rm -f "${candidate_service}"
  fi

  if [[ "${active_slot}" == "legacy" ]]; then
    rm -f "${ACTIVE_SLOT_FILE}"
  else
    atomic_write_line "${ACTIVE_SLOT_FILE}" "${active_slot}" 600
  fi

  summary "status=rolled_back"
  summary "failed_candidate=${REQUESTED_IMAGE}"
  summary "restored_slot=${active_slot}"
  summary "restored_port=${active_port}"
  exit "${exit_code}"
}

for command in docker curl python3 nginx systemctl flock; do
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
is_immutable_image "${BACKEND_IMAGE}" || {
  log error "BACKEND_IMAGE must use a Git SHA tag or sha256 digest"
  exit 1
}
[[ -f "${PROJECT_DIR}/${COMPOSE_FILE}" ]] || {
  log error "compose file is missing: ${PROJECT_DIR}/${COMPOSE_FILE}"
  exit 1
}
[[ -f "${NGINX_SITE_FILE}" ]] || {
  log error "nginx site is missing: ${NGINX_SITE_FILE}"
  exit 1
}

cd "${PROJECT_DIR}"
if [[ "${DEPLOY_LOCK_ALREADY_HELD}" != "true" ]]; then
  exec 9>"${DEPLOY_LOCK_FILE}"
  flock -n 9 || {
    log error "another deployment holds ${DEPLOY_LOCK_FILE}"
    exit 1
  }
fi

mkdir -p media model-cache/u2net
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT
: > "${SUMMARY_FILE}"
COMPOSE=(docker compose -f "${COMPOSE_FILE}" --profile bluegreen)

resolve_active_slot
ensure_managed_nginx_upstream
ensure_internal_proxy
previous_image="$(sed -n 's/^BACKEND_IMAGE=//p' "${ENV_FILE}" | tail -n 1)"
is_immutable_image "${previous_image}" || {
  log error "current BACKEND_IMAGE in ${ENV_FILE} is not immutable"
  exit 1
}

if [[ "${BOOTSTRAP_ONLY}" == "true" ]]; then
  smoke_candidate "http://127.0.0.1:${active_port}"
  wait_ready_url "internal_proxy" "http://127.0.0.1:${INTERNAL_PROXY_PORT}/api/ready"
  summary "status=bootstrap_complete"
  summary "active_slot=${active_slot}"
  summary "active_port=${active_port}"
  summary "internal_proxy_port=${INTERNAL_PROXY_PORT}"
  log "done" "nginx blue-green prerequisites are ready; no containers changed"
  exit 0
fi

if [[ "${active_slot}" != "legacy" && "${BACKEND_IMAGE}" == "${previous_image}" ]]; then
  smoke_candidate "http://127.0.0.1:${active_port}"
  wait_ready_url "origin" "https://${API_HOST}/api/ready" --resolve "${API_HOST}:443:127.0.0.1"
  wait_ready_url "public" "${PUBLIC_READY_URL}"
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

log pull "pulling candidate services ${candidate_service} and bot"
"${COMPOSE[@]}" pull "${candidate_service}" bot

if [[ "${RUN_MIGRATIONS}" == "true" ]]; then
  "${COMPOSE[@]}" run -T --rm --no-deps "${candidate_service}" alembic upgrade head
fi
if [[ "${RUN_DEFAULTS}" == "true" ]]; then
  "${COMPOSE[@]}" run -T --rm --no-deps "${candidate_service}" python3 scripts/ensure_global_config_defaults.py
fi

log start "starting ${candidate_service} on 127.0.0.1:${candidate_port}"
candidate_started=true
"${COMPOSE[@]}" up -d --no-deps --force-recreate "${candidate_service}"
smoke_candidate "http://127.0.0.1:${candidate_port}"

write_backend_image "${BACKEND_IMAGE}"
env_updated=true
bot_update_attempted=true
"${COMPOSE[@]}" up -d --no-deps --force-recreate bot
wait_service_running bot

nginx_switch_attempted=true
write_upstream "${candidate_port}"
nginx -t
systemctl reload nginx
log switch "nginx now routes to ${candidate_slot} on ${candidate_port}"

wait_ready_url "origin" "https://${API_HOST}/api/ready" --resolve "${API_HOST}:443:127.0.0.1"
wait_ready_url "public" "${PUBLIC_READY_URL}"
sleep "${DRAIN_SECONDS}"

old_service_stopped=true
"${COMPOSE[@]}" stop "${active_service}"
"${COMPOSE[@]}" rm -f "${active_service}"
atomic_write_line "${PREVIOUS_IMAGE_FILE}" "${previous_image}" 600
atomic_write_line "${ACTIVE_SLOT_FILE}" "${candidate_slot}" 600

trap - ERR
summary "status=activated"
summary "previous_slot=${active_slot}"
summary "active_slot=${candidate_slot}"
summary "active_port=${candidate_port}"
summary "backend_image=${BACKEND_IMAGE}"
summary "previous_image=${previous_image}"
log "done" "activated ${candidate_slot}; previous service ${active_service} is stopped"
