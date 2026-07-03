#!/usr/bin/env bash
set -euo pipefail

API_HOST="${API_HOST:-api.mvn.by}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://${API_HOST}}"
PRIMARY_ORIGIN="${PRIMARY_ORIGIN:-185.250.45.54}"
STANDBY_ORIGIN="${STANDBY_ORIGIN:-193.47.42.213}"
PRIMARY_ROLE="${PRIMARY_ROLE:-primary}"
STANDBY_ROLE="${STANDBY_ROLE:-standby}"
CHECK_PUBLIC_READY="${CHECK_PUBLIC_READY:-true}"
CURL_CONNECT_TIMEOUT="${CURL_CONNECT_TIMEOUT:-5}"
CURL_MAX_TIME="${CURL_MAX_TIME:-15}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

log() {
  printf '[ha-check] %s\n' "$*" >&2
}

curl_json() {
  local label="$1"
  local url="$2"
  local output_file="$3"
  shift 3

  log "GET ${label}: ${url}"
  curl -ksS \
    --connect-timeout "${CURL_CONNECT_TIMEOUT}" \
    --max-time "${CURL_MAX_TIME}" \
    -o "${output_file}" \
    -w '%{http_code}' \
    "$@" \
    "${url}"
}

is_true() {
  case "${1:-}" in
    true|TRUE|True|1|yes|YES|Yes|on|ON|On) return 0 ;;
    *) return 1 ;;
  esac
}

validate_payload() {
  local label="$1"
  local file="$2"
  local expected_role="$3"
  local expected_ready="$4"

  python3 - "$label" "$file" "$expected_role" "$expected_ready" <<'PY'
import json
import sys

label, path, expected_role, expected_ready = sys.argv[1:5]
with open(path, "r", encoding="utf-8") as fh:
    payload = json.load(fh)

role = payload.get("app_role")
if role != expected_role:
    raise SystemExit(f"{label}: expected app_role={expected_role!r}, got {role!r}")

api_state = payload.get("api")
traffic = payload.get("traffic")
if expected_ready == "ready":
    if payload.get("status") != "ok" or api_state != "ready" or traffic != "enabled":
        raise SystemExit(f"{label}: payload is not ready: {payload}")
    if payload.get("database") != "online":
        raise SystemExit(f"{label}: database is not online: {payload}")
    if payload.get("database_writable") is not True:
        raise SystemExit(f"{label}: database is not writable: {payload}")
else:
    if api_state != "not_ready" or traffic != "disabled":
        raise SystemExit(f"{label}: payload is not fenced standby: {payload}")

print(f"{label}: role={role} api={api_state} traffic={traffic}")
PY
}

public_file="${TMP_DIR}/public-ready.json"
primary_file="${TMP_DIR}/primary-ready.json"
standby_file="${TMP_DIR}/standby-ready.json"

if is_true "${CHECK_PUBLIC_READY}"; then
  public_code="$(curl_json "public ready" "${PUBLIC_BASE_URL%/}/api/ready" "${public_file}")"
  printf '\n'
  if [[ "${public_code}" != "200" ]]; then
    log "public /api/ready expected HTTP 200, got ${public_code}"
    cat "${public_file}" || true
    exit 1
  fi
  validate_payload "public" "${public_file}" "${PRIMARY_ROLE}" ready
else
  log "public ready check skipped"
fi

primary_code="$(curl_json "primary direct ready" "https://${API_HOST}/api/ready" "${primary_file}" --resolve "${API_HOST}:443:${PRIMARY_ORIGIN}")"
printf '\n'
if [[ "${primary_code}" != "200" ]]; then
  log "primary direct /api/ready expected HTTP 200, got ${primary_code}"
  cat "${primary_file}" || true
  exit 1
fi
validate_payload "primary" "${primary_file}" "${PRIMARY_ROLE}" ready

standby_code="$(curl_json "standby direct ready" "https://${API_HOST}/api/ready" "${standby_file}" --resolve "${API_HOST}:443:${STANDBY_ORIGIN}")"
printf '\n'
if [[ "${standby_code}" == "200" ]]; then
  log "standby direct /api/ready returned HTTP 200; split-brain risk"
  cat "${standby_file}" || true
  exit 1
fi
validate_payload "standby" "${standby_file}" "${STANDBY_ROLE}" not_ready

log "active-passive invariant passed: primary ready, standby fenced"
