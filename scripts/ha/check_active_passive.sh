#!/usr/bin/env bash
set -euo pipefail

API_HOST="${API_HOST:-api.mvn.by}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://${API_HOST}}"
PRIMARY_ORIGIN="${PRIMARY_ORIGIN:-185.250.45.54}"
STANDBY_ORIGIN="${STANDBY_ORIGIN:-193.47.42.213}"
PRIMARY_ROLE="${PRIMARY_ROLE:-primary}"
STANDBY_ROLE="${STANDBY_ROLE:-standby}"
CHECK_PUBLIC_READY="${CHECK_PUBLIC_READY:-true}"
DISCOVER_PRIMARY_FROM_READY="${DISCOVER_PRIMARY_FROM_READY:-false}"
CURL_CONNECT_TIMEOUT="${CURL_CONNECT_TIMEOUT:-5}"
CURL_MAX_TIME="${CURL_MAX_TIME:-15}"
READY_RETRIES="${READY_RETRIES:-3}"
READY_RETRY_SLEEP="${READY_RETRY_SLEEP:-5}"

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
from json import JSONDecodeError

label, path, expected_role, expected_ready = sys.argv[1:5]
try:
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
except (OSError, JSONDecodeError) as exc:
    raise SystemExit(f"{label}: response is not valid readiness JSON: {exc}") from exc

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

print_response_excerpt() {
  local label="$1"
  local file="$2"
  if [[ ! -s "${file}" ]]; then
    log "${label} response body is empty"
    return
  fi
  log "${label} response body excerpt:"
  head -c 500 "${file}" >&2 || true
  printf '\n' >&2
}

check_ready_with_retries() {
  local label="$1"
  local url="$2"
  local output_file="$3"
  local expected_role="$4"
  local expected_ready="$5"
  shift 5

  local attempt code
  for attempt in $(seq 1 "${READY_RETRIES}"); do
    if code="$(curl_json "${label}" "${url}" "${output_file}" "$@")"; then
      printf '\n'
    else
      code="curl_failed"
      printf '\n'
    fi

    if [[ "${expected_ready}" == "ready" ]]; then
      if [[ "${code}" == "200" ]] && validate_payload "${label}" "${output_file}" "${expected_role}" ready; then
        return 0
      fi
      log "${label} attempt ${attempt}/${READY_RETRIES} failed: expected HTTP 200 with ready JSON, got ${code}"
    else
      if [[ "${code}" == "200" ]]; then
        log "${label} returned HTTP 200; split-brain risk"
        print_response_excerpt "${label}" "${output_file}"
        exit 1
      fi
      if validate_payload "${label}" "${output_file}" "${expected_role}" not_ready; then
        return 0
      fi
      log "${label} attempt ${attempt}/${READY_RETRIES} failed: expected fenced standby JSON with non-200 HTTP, got ${code}"
    fi

    print_response_excerpt "${label}" "${output_file}"
    if (( attempt < READY_RETRIES )); then
      log "${label} retrying in ${READY_RETRY_SLEEP}s"
      sleep "${READY_RETRY_SLEEP}"
    fi
  done

  log "${label} failed after ${READY_RETRIES} attempts"
  return 1
}

discover_primary_origin() {
  local configured_primary_file="$1"
  local configured_standby_file="$2"
  local attempt primary_code standby_code swap

  for attempt in $(seq 1 "${READY_RETRIES}"); do
    primary_code="$(
      curl_json \
        "configured primary origin discovery" \
        "https://${API_HOST}/api/ready" \
        "${configured_primary_file}" \
        --resolve "${API_HOST}:443:${PRIMARY_ORIGIN}" \
        || true
    )"
    standby_code="$(
      curl_json \
        "configured standby origin discovery" \
        "https://${API_HOST}/api/ready" \
        "${configured_standby_file}" \
        --resolve "${API_HOST}:443:${STANDBY_ORIGIN}" \
        || true
    )"

    if [[ "${primary_code}" == "200" && "${standby_code}" == "200" ]]; then
      log "both origins returned HTTP 200 during discovery; split-brain risk"
      return 1
    fi
    if [[ "${primary_code}" == "200" && "${standby_code}" != "200" ]]; then
      log "discovered active origin=${PRIMARY_ORIGIN} standby=${STANDBY_ORIGIN}"
      return 0
    fi
    if [[ "${primary_code}" != "200" && "${standby_code}" == "200" ]]; then
      swap="${PRIMARY_ORIGIN}"
      PRIMARY_ORIGIN="${STANDBY_ORIGIN}"
      STANDBY_ORIGIN="${swap}"
      log "discovered active origin=${PRIMARY_ORIGIN} standby=${STANDBY_ORIGIN}"
      return 0
    fi

    log "origin discovery attempt ${attempt}/${READY_RETRIES} found no ready origin: configured_primary=${primary_code:-curl_failed} configured_standby=${standby_code:-curl_failed}"
    if (( attempt < READY_RETRIES )); then
      sleep "${READY_RETRY_SLEEP}"
    fi
  done

  return 1
}

public_file="${TMP_DIR}/public-ready.json"
primary_file="${TMP_DIR}/primary-ready.json"
standby_file="${TMP_DIR}/standby-ready.json"

if is_true "${DISCOVER_PRIMARY_FROM_READY}"; then
  discover_primary_origin "${primary_file}" "${standby_file}"
fi

if is_true "${CHECK_PUBLIC_READY}"; then
  check_ready_with_retries "public ready" "${PUBLIC_BASE_URL%/}/api/ready" "${public_file}" "${PRIMARY_ROLE}" ready
else
  log "public ready check skipped"
fi

check_ready_with_retries \
  "primary direct ready" \
  "https://${API_HOST}/api/ready" \
  "${primary_file}" \
  "${PRIMARY_ROLE}" \
  ready \
  --resolve "${API_HOST}:443:${PRIMARY_ORIGIN}"

check_ready_with_retries \
  "standby direct ready" \
  "https://${API_HOST}/api/ready" \
  "${standby_file}" \
  "${STANDBY_ROLE}" \
  not_ready \
  --resolve "${API_HOST}:443:${STANDBY_ORIGIN}"

log "active-passive invariant passed: primary ready, standby fenced"
