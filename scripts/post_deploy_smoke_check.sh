#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:18080}"
SMOKE_SUMMARY_FILE="${SMOKE_SUMMARY_FILE:-/tmp/smoke_summary.txt}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/air-api/docker-compose.prod.yml}"
COMPOSE_SERVICE_CHECKS="${COMPOSE_SERVICE_CHECKS:-app bot}"
ACTIVE_SLOT_FILE="${API_ACTIVE_SLOT_FILE:-$(dirname "${COMPOSE_FILE}")/.active-api-slot}"
BOT_RUNTIME_CHECK_SERVICE="${BOT_RUNTIME_CHECK_SERVICE:-bot}"
BOT_EXPECT_ENABLED="${BOT_EXPECT_ENABLED:-true}"
READY_URL="${READY_URL:-}"
MAX_RETRIES=${MAX_RETRIES:-20}
RETRY_DELAY=${RETRY_DELAY:-2}
BACKEND_IMAGE="${BACKEND_IMAGE:-}"
if [[ -n "${BACKEND_IMAGE}" ]]; then
  export BACKEND_IMAGE
fi

log() {
  local stage="$1"
  shift
  echo "[smoke][${stage}] $*"
}

summary() {
  echo "$*" >> "${SMOKE_SUMMARY_FILE}"
}

: > "${SMOKE_SUMMARY_FILE}"

if ! command -v curl >/dev/null 2>&1; then
  log preflight "curl is not installed"
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  log preflight "python3 is not installed"
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  log preflight "docker is not installed"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  log preflight "docker compose is not available"
  exit 1
fi

COMPOSE=(docker compose -f "${COMPOSE_FILE}" --profile bluegreen)
ACTIVE_APP_SERVICE="app"
if [[ -f "${ACTIVE_SLOT_FILE}" ]]; then
  active_slot="$(tr -d '\r\n' < "${ACTIVE_SLOT_FILE}")"
  case "${active_slot}" in
    blue|green) ACTIVE_APP_SERVICE="app-${active_slot}" ;;
    *)
      log preflight "invalid active API slot: ${active_slot}"
      exit 1
      ;;
  esac
fi

resolved_service_checks=()
for service in ${COMPOSE_SERVICE_CHECKS}; do
  if [[ "${service}" == "app" ]]; then
    resolved_service_checks+=("${ACTIVE_APP_SERVICE}")
  else
    resolved_service_checks+=("${service}")
  fi
done
COMPOSE_SERVICE_CHECKS="${resolved_service_checks[*]}"

HEALTH_URL_PRIMARY="${BASE_URL}/health"
HEALTH_URL_FALLBACK="${BASE_URL}/api/health"
PRODUCTS_URL="${BASE_URL}/api/v1/products?limit=5"
FILTERS_URL="${BASE_URL}/api/v1/filters/config"
HEALTH_URL_USED=""

# Wait for application to be ready with retry logic
log wait "Waiting for application to be ready (max ${MAX_RETRIES} attempts, ${RETRY_DELAY}s between retries)..."

health_payload=""
for attempt in $(seq 1 "${MAX_RETRIES}"); do
  log attempt "Health check attempt $attempt/$MAX_RETRIES"
  health_payload="$(curl -fsS "${HEALTH_URL_PRIMARY}" 2>/dev/null || true)"
  
  if [[ -n "${health_payload}" ]]; then
    HEALTH_URL_USED="${HEALTH_URL_PRIMARY}"
    log success "✅ Got response from ${HEALTH_URL_PRIMARY}"
    break
  fi
  
  # Try fallback endpoint
  health_payload="$(curl -fsS "${HEALTH_URL_FALLBACK}" 2>/dev/null || true)"
  if [[ -n "${health_payload}" ]]; then
    HEALTH_URL_USED="${HEALTH_URL_FALLBACK}"
    log success "✅ Got response from ${HEALTH_URL_FALLBACK}"
    break
  fi
  
  if [ "${attempt}" -lt "${MAX_RETRIES}" ]; then
    log retry "Waiting ${RETRY_DELAY}s before retry..."
    sleep "${RETRY_DELAY}"
  fi
done

# Check if we got a valid response
if [[ -z "${health_payload}" ]]; then
  log error "❌ Failed to connect to health endpoint after $MAX_RETRIES attempts"
  summary "smoke_status=failed"
  summary "base_url=${BASE_URL}"
  summary "failure_reason=no_response_from_health_endpoint"
  exit 1
fi

log request "GET ${PRODUCTS_URL}"
products_payload="$(curl -fsS "${PRODUCTS_URL}")"

log request "GET ${FILTERS_URL}"
filters_payload="$(curl -fsS "${FILTERS_URL}")"

HEALTH_PAYLOAD="${health_payload}" \
PRODUCTS_PAYLOAD="${products_payload}" \
FILTERS_PAYLOAD="${filters_payload}" \
python3 - <<'PY'
import json
import os

health = json.loads(os.environ["HEALTH_PAYLOAD"])
products = json.loads(os.environ["PRODUCTS_PAYLOAD"])
filters_cfg = json.loads(os.environ["FILTERS_PAYLOAD"])

if "status" not in health:
    raise SystemExit("health payload missing status")

items = products.get("items")
if not isinstance(items, list):
    raise SystemExit("products payload missing list items")

for required_key in ("price", "area", "brands", "expert_tags"):
    if required_key not in filters_cfg:
        raise SystemExit(f"filters config missing key: {required_key}")

print(f"health_status={health.get('status')}")
print(f"products_count={len(items)}")
print(f"filters_keys={','.join(sorted(filters_cfg.keys()))}")
PY

checks_done="health,products,filters_config"
if [[ -n "${READY_URL}" ]]; then
  log request "GET ${READY_URL}"
  ready_payload="$(curl -fsS "${READY_URL}")"
  READY_PAYLOAD="${ready_payload}" python3 - <<'PY'
import json
import os

ready = json.loads(os.environ["READY_PAYLOAD"])
if ready.get("status") != "ok" or ready.get("api") != "ready":
    raise SystemExit("readiness payload is not ready")

print(f"ready_status={ready.get('status')}")
print(f"ready_traffic={ready.get('traffic')}")
print(f"ready_database={ready.get('database')}")
PY
  checks_done="${checks_done},readiness"
fi

log request "docker compose ps --status running --services"
running_services="$("${COMPOSE[@]}" ps --status running --services 2>/dev/null || true)"
for service in ${COMPOSE_SERVICE_CHECKS}; do
  if ! printf '%s\n' "${running_services}" | grep -Fxq "${service}"; then
    log error "❌ Compose service is not running: ${service}"
    summary "smoke_status=failed"
    summary "base_url=${BASE_URL}"
    summary "failure_reason=compose_service_not_running:${service}"
    "${COMPOSE[@]}" ps || true
    exit 1
  fi
done
log success "✅ Compose services running: ${COMPOSE_SERVICE_CHECKS}"

checks_done="${checks_done},compose_services"
if [[ "${BOT_EXPECT_ENABLED}" == "true" ]]; then
  log request "docker compose exec ${BOT_RUNTIME_CHECK_SERVICE} python3 - read bot runtime decision"
  bot_runtime_payload="$("${COMPOSE[@]}" exec -T "${BOT_RUNTIME_CHECK_SERVICE}" python3 - <<'PY'
from core.config import settings

decision = settings.bot_control_decision
print(f"enabled={str(decision.enabled).lower()}")
print(f"reason={decision.reason}")
PY
)"
  log info "bot_runtime_decision=${bot_runtime_payload//$'\n'/; }"
  if ! printf '%s\n' "${bot_runtime_payload}" | grep -Fxq "enabled=true"; then
    log error "❌ Bot runtime decision is not enabled"
    summary "smoke_status=failed"
    summary "base_url=${BASE_URL}"
    summary "failure_reason=bot_runtime_disabled"
    summary "bot_runtime_decision=${bot_runtime_payload//$'\n'/; }"
    exit 1
  fi
  log success "✅ Bot runtime decision is enabled"
  checks_done="${checks_done},bot_runtime"
fi

summary "smoke_status=passed"
summary "base_url=${BASE_URL}"
summary "health_url_used=${HEALTH_URL_USED}"
summary "checks=${checks_done}"
log info "health_url_used=${HEALTH_URL_USED}"
log "done" "smoke checks passed"
