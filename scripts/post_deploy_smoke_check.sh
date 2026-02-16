#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
SMOKE_SUMMARY_FILE="${SMOKE_SUMMARY_FILE:-/tmp/smoke_summary.txt}"

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

HEALTH_URL="${BASE_URL}/health"
PRODUCTS_URL="${BASE_URL}/api/v1/products?limit=5"
FILTERS_URL="${BASE_URL}/api/v1/filters/config"

log request "GET ${HEALTH_URL}"
health_payload="$(curl -fsS "${HEALTH_URL}")"

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

summary "smoke_status=passed"
summary "base_url=${BASE_URL}"
summary "checks=health,products,filters_config"
log done "smoke checks passed"
