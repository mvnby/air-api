#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://api.mvn.by}"
CURL_CONNECT_TIMEOUT="${CURL_CONNECT_TIMEOUT:-5}"
CURL_MAX_TIME="${CURL_MAX_TIME:-15}"

API_SSH_HOST="${API_SSH_HOST:-}"
API_SSH_USER="${API_SSH_USER:-}"
API_SSH_PORT="${API_SSH_PORT:-22}"
API_SSH_KEY_PATH="${API_SSH_KEY_PATH:-}"
API_SSH_STRICT_HOST_KEY_CHECKING="${API_SSH_STRICT_HOST_KEY_CHECKING:-accept-new}"
API_SSH_CONNECT_TIMEOUT="${API_SSH_CONNECT_TIMEOUT:-10}"
API_PROJECT_DIR="${API_PROJECT_DIR:-/opt/air-api}"
API_COMPOSE_FILE="${API_COMPOSE_FILE:-docker-compose.prod.yml}"
API_COMPOSE_SERVICE_CHECKS="${API_COMPOSE_SERVICE_CHECKS:-app bot db}"
API_LOCAL_HEALTH_URL="${API_LOCAL_HEALTH_URL:-http://127.0.0.1:8000/api/health}"
API_TLS_HOST="${API_TLS_HOST:-api.mvn.by}"

DISK_WARN_PCT="${DISK_WARN_PCT:-80}"
DISK_CRITICAL_PCT="${DISK_CRITICAL_PCT:-90}"
INODE_WARN_PCT="${INODE_WARN_PCT:-80}"
INODE_CRITICAL_PCT="${INODE_CRITICAL_PCT:-90}"
TLS_WARN_DAYS="${TLS_WARN_DAYS:-14}"
TLS_CRITICAL_DAYS="${TLS_CRITICAL_DAYS:-3}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-36}"
CHECK_BACKUPS="${CHECK_BACKUPS:-true}"
SKIP_PUBLIC_CHECKS="${SKIP_PUBLIC_CHECKS:-false}"

PUBLIC_ONLY=false
critical_failures=0
warnings=0
TMP_DIR=""

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/check_api_vps_health.sh [--public-only]

Checks the current API VPS without printing secret values.

Default behavior:
  1. Checks public API endpoints from BASE_URL unless SKIP_PUBLIC_CHECKS=true.
  2. Runs SSH host checks only when API_SSH_HOST and API_SSH_USER are set.
  3. Works as public-only automatically when SSH env is absent.

Options:
  --public-only  Skip SSH, Docker, database, TLS-origin, and backup checks.
  -h, --help     Show this help text.

Common env:
  BASE_URL=https://api.mvn.by
  API_SSH_HOST=mvn-api
  API_SSH_USER=root
  API_SSH_KEY_PATH=~/.ssh/id_ed25519
  API_PROJECT_DIR=/opt/air-api
  API_COMPOSE_FILE=docker-compose.prod.yml
  API_COMPOSE_SERVICE_CHECKS="app bot db"
  API_LOCAL_HEALTH_URL=http://127.0.0.1:8000/api/health
  BACKUP_MAX_AGE_HOURS=36
  CHECK_BACKUPS=true
  SKIP_PUBLIC_CHECKS=false

Exit code:
  0 when critical checks pass.
  non-zero when public endpoints, SSH host checks, containers, DB readiness,
  localhost health, TLS critical expiry, or backup freshness checks fail.
USAGE
}

log() {
  local stage="$1"
  shift
  printf '[api-vps][%s] %s\n' "${stage}" "$*"
}

ok() {
  log ok "$*"
}

warn() {
  warnings=$((warnings + 1))
  log warn "$*"
}

fail() {
  critical_failures=$((critical_failures + 1))
  log fail "$*"
}

cleanup() {
  if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
}
trap cleanup EXIT

is_unsigned_int() {
  case "$1" in
    ''|*[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

is_unsigned_number() {
  [[ "$1" =~ ^[0-9]+([.][0-9]+)?$ ]]
}

normalize_bool() {
  case "$1" in
    true|TRUE|True|1|yes|YES|Yes|on|ON|On) printf 'true' ;;
    false|FALSE|False|0|no|NO|No|off|OFF|Off) printf 'false' ;;
    *) return 1 ;;
  esac
}

for arg in "$@"; do
  case "${arg}" in
    --public-only)
      PUBLIC_ONLY=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log error "unsupported argument: ${arg}"
      usage
      exit 2
      ;;
  esac
done

BASE_URL="${BASE_URL%/}"
if [[ "${API_SSH_KEY_PATH}" == "~/"* && -n "${HOME:-}" ]]; then
  API_SSH_KEY_PATH="${HOME}/${API_SSH_KEY_PATH#~/}"
fi
if [[ -z "${BASE_URL}" ]]; then
  fail "BASE_URL cannot be empty"
fi

if ! is_unsigned_int "${CURL_CONNECT_TIMEOUT}" || ! is_unsigned_int "${CURL_MAX_TIME}"; then
  fail "CURL_CONNECT_TIMEOUT and CURL_MAX_TIME must be positive integers"
fi
if ! is_unsigned_int "${API_SSH_PORT}" || ! is_unsigned_int "${API_SSH_CONNECT_TIMEOUT}"; then
  fail "API_SSH_PORT and API_SSH_CONNECT_TIMEOUT must be positive integers"
fi
if ! is_unsigned_int "${DISK_WARN_PCT}" || ! is_unsigned_int "${DISK_CRITICAL_PCT}"; then
  fail "DISK_WARN_PCT and DISK_CRITICAL_PCT must be integer percentages"
fi
if ! is_unsigned_int "${INODE_WARN_PCT}" || ! is_unsigned_int "${INODE_CRITICAL_PCT}"; then
  fail "INODE_WARN_PCT and INODE_CRITICAL_PCT must be integer percentages"
fi
if ! is_unsigned_int "${TLS_WARN_DAYS}" || ! is_unsigned_int "${TLS_CRITICAL_DAYS}"; then
  fail "TLS_WARN_DAYS and TLS_CRITICAL_DAYS must be integer day counts"
fi
if ! is_unsigned_number "${BACKUP_MAX_AGE_HOURS}"; then
  fail "BACKUP_MAX_AGE_HOURS must be a non-negative number"
fi
if ! CHECK_BACKUPS="$(normalize_bool "${CHECK_BACKUPS}")"; then
  fail "CHECK_BACKUPS must be true or false"
fi
if ! SKIP_PUBLIC_CHECKS="$(normalize_bool "${SKIP_PUBLIC_CHECKS}")"; then
  fail "SKIP_PUBLIC_CHECKS must be true or false"
fi

if (( critical_failures > 0 )); then
  log summary "status=failed critical_failures=${critical_failures} warnings=${warnings}"
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  fail "curl is not installed locally"
fi
if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 is not installed locally"
fi
if [[ "${PUBLIC_ONLY}" != "true" && ( -n "${API_SSH_HOST}" || -n "${API_SSH_USER}" ) ]]; then
  if ! command -v ssh >/dev/null 2>&1; then
    fail "ssh is not installed locally"
  fi
  if [[ -z "${API_SSH_HOST}" || -z "${API_SSH_USER}" ]]; then
    fail "set both API_SSH_HOST and API_SSH_USER for SSH checks, or pass --public-only"
  fi
  if [[ -n "${API_SSH_KEY_PATH}" && ! -r "${API_SSH_KEY_PATH}" ]]; then
    fail "API_SSH_KEY_PATH is not readable: ${API_SSH_KEY_PATH}"
  fi
fi

if (( critical_failures > 0 )); then
  log summary "status=failed critical_failures=${critical_failures} warnings=${warnings}"
  exit 1
fi

curl_to_file() {
  local label="$1"
  local url="$2"
  local output_file="$3"
  local curl_output

  log public "GET ${url}"
  if curl_output="$(curl -fsS --connect-timeout "${CURL_CONNECT_TIMEOUT}" --max-time "${CURL_MAX_TIME}" -o "${output_file}" "${url}" 2>&1)"; then
    ok "public ${label} responded"
    return 0
  fi

  fail "public ${label} failed: ${curl_output}"
  return 1
}

run_public_checks() {
  local health_file products_file filters_file public_ok validation_output

  TMP_DIR="$(mktemp -d)"
  health_file="${TMP_DIR}/health.json"
  products_file="${TMP_DIR}/products.json"
  filters_file="${TMP_DIR}/filters.json"
  public_ok=true

  curl_to_file "health" "${BASE_URL}/api/health" "${health_file}" || public_ok=false
  curl_to_file "products" "${BASE_URL}/api/v1/products?limit=5" "${products_file}" || public_ok=false
  curl_to_file "filters config" "${BASE_URL}/api/v1/filters/config" "${filters_file}" || public_ok=false

  if [[ "${public_ok}" != "true" ]]; then
    return 0
  fi

  if validation_output="$(python3 - "${health_file}" "${products_file}" "${filters_file}" <<'PY' 2>&1
import json
import sys

health_path, products_path, filters_path = sys.argv[1:4]

with open(health_path, "r", encoding="utf-8") as fh:
    health = json.load(fh)
with open(products_path, "r", encoding="utf-8") as fh:
    products = json.load(fh)
with open(filters_path, "r", encoding="utf-8") as fh:
    filters_cfg = json.load(fh)

if health.get("status") != "ok":
    raise SystemExit(f"health status is not ok: {health.get('status')!r}")
if health.get("database") != "online":
    raise SystemExit(f"database status is not online: {health.get('database')!r}")

items = products.get("items")
if not isinstance(items, list):
    raise SystemExit("products payload missing list items")
if len(items) < 1:
    raise SystemExit("products endpoint returned zero items")

for required_key in ("price", "area", "brands", "expert_tags"):
    if required_key not in filters_cfg:
        raise SystemExit(f"filters config missing key: {required_key}")

print(f"public_health_status={health.get('status')}")
print(f"public_database_status={health.get('database')}")
print(f"public_products_count={len(items)}")
print(f"public_filters_keys={','.join(sorted(filters_cfg.keys()))}")
PY
)"; then
    while IFS= read -r line; do
      if [[ -n "${line}" ]]; then
        log public "${line}"
      fi
    done <<< "${validation_output}"
    ok "public API payload validation passed"
  else
    fail "public API payload validation failed: ${validation_output}"
  fi
}

run_ssh_checks() {
  local api_compose_service_checks_arg
  api_compose_service_checks_arg="${API_COMPOSE_SERVICE_CHECKS// /,}"
  local ssh_cmd=(
    ssh
    -p "${API_SSH_PORT}"
    -o BatchMode=yes
    -o "StrictHostKeyChecking=${API_SSH_STRICT_HOST_KEY_CHECKING}"
    -o "ConnectTimeout=${API_SSH_CONNECT_TIMEOUT}"
    -o ServerAliveInterval=15
    -o ServerAliveCountMax=2
  )

  if [[ -n "${API_SSH_KEY_PATH}" ]]; then
    ssh_cmd+=(-i "${API_SSH_KEY_PATH}")
  fi
  ssh_cmd+=("${API_SSH_USER}@${API_SSH_HOST}")

  log ssh "running optional host checks on ${API_SSH_USER}@${API_SSH_HOST}:${API_SSH_PORT}"
  if "${ssh_cmd[@]}" bash -s -- \
    "${API_PROJECT_DIR}" \
    "${API_COMPOSE_FILE}" \
    "${DISK_WARN_PCT}" \
    "${DISK_CRITICAL_PCT}" \
    "${INODE_WARN_PCT}" \
    "${INODE_CRITICAL_PCT}" \
    "${TLS_WARN_DAYS}" \
    "${TLS_CRITICAL_DAYS}" \
    "${BACKUP_MAX_AGE_HOURS}" \
    "${CHECK_BACKUPS}" \
    "${API_TLS_HOST}" \
    "${api_compose_service_checks_arg}" \
    "${API_LOCAL_HEALTH_URL}" <<'REMOTE'
set -euo pipefail

PROJECT_DIR="$1"
COMPOSE_FILE="$2"
DISK_WARN_PCT="$3"
DISK_CRITICAL_PCT="$4"
INODE_WARN_PCT="$5"
INODE_CRITICAL_PCT="$6"
TLS_WARN_DAYS="$7"
TLS_CRITICAL_DAYS="$8"
BACKUP_MAX_AGE_HOURS="$9"
CHECK_BACKUPS="${10}"
API_TLS_HOST="${11}"
API_COMPOSE_SERVICE_CHECKS="${12//,/ }"
API_LOCAL_HEALTH_URL="${13}"

remote_failures=0
remote_warnings=0

remote_log() {
  local stage="$1"
  shift
  printf '[api-vps][ssh:%s] %s\n' "${stage}" "$*"
}

remote_ok() {
  remote_log ok "$*"
}

remote_warn() {
  remote_warnings=$((remote_warnings + 1))
  remote_log warn "$*"
}

remote_fail() {
  remote_failures=$((remote_failures + 1))
  remote_log fail "$*"
}

is_int() {
  case "$1" in
    ''|*[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

print_prefixed() {
  local stage="$1"
  local content="$2"
  while IFS= read -r line; do
    if [[ -n "${line}" ]]; then
      remote_log "${stage}" "${line}"
    fi
  done <<< "${content}"
}

check_pct() {
  local label="$1"
  local value="$2"
  local warn_pct="$3"
  local critical_pct="$4"
  local detail="$5"

  if ! is_int "${value}"; then
    remote_warn "${label} usage is unavailable (${detail})"
    return
  fi

  if (( value >= critical_pct )); then
    remote_fail "${label} usage critical: ${value}% (${detail})"
  elif (( value >= warn_pct )); then
    remote_warn "${label} usage high: ${value}% (${detail})"
  else
    remote_ok "${label} usage ${value}% (${detail})"
  fi
}

if [[ ! -d "${PROJECT_DIR}" ]]; then
  remote_fail "project dir not found: ${PROJECT_DIR}"
else
  remote_ok "project dir exists: ${PROJECT_DIR}"
fi

if [[ -d "${PROJECT_DIR}" && ! -f "${PROJECT_DIR}/${COMPOSE_FILE}" ]]; then
  remote_fail "compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}"
fi

disk_pct="$(df -P / | awk 'NR == 2 {gsub("%", "", $5); print $5}' || true)"
disk_detail="$(df -P / | awk 'NR == 2 {print "mount=" $6 " avail_kb=" $4}' || true)"
check_pct "disk" "${disk_pct}" "${DISK_WARN_PCT}" "${DISK_CRITICAL_PCT}" "${disk_detail:-unknown}"

inode_pct="$(df -Pi / | awk 'NR == 2 {gsub("%", "", $5); print $5}' || true)"
inode_detail="$(df -Pi / | awk 'NR == 2 {print "mount=" $6 " iavail=" $4}' || true)"
check_pct "inode" "${inode_pct}" "${INODE_WARN_PCT}" "${INODE_CRITICAL_PCT}" "${inode_detail:-unknown}"

if ! command -v docker >/dev/null 2>&1; then
  remote_fail "docker is not installed"
elif ! docker compose version >/dev/null 2>&1; then
  remote_fail "docker compose is not available"
elif [[ -d "${PROJECT_DIR}" && -f "${PROJECT_DIR}/${COMPOSE_FILE}" ]]; then
  cd "${PROJECT_DIR}"
  COMPOSE=(docker compose -f "${COMPOSE_FILE}")

  if compose_ps_output="$("${COMPOSE[@]}" ps 2>&1)"; then
    remote_ok "docker compose ps succeeded"
    print_prefixed compose "${compose_ps_output}"
  else
    remote_fail "docker compose ps failed: ${compose_ps_output}"
  fi

  running_services="$("${COMPOSE[@]}" ps --services --filter status=running 2>/dev/null || true)"
  for service in ${API_COMPOSE_SERVICE_CHECKS}; do
    if printf '%s\n' "${running_services}" | grep -Fxq "${service}"; then
      remote_ok "container running: ${service}"
    else
      remote_fail "container is not running: ${service}"
    fi
  done

  if "${COMPOSE[@]}" exec -T db sh -lc 'pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null' >/dev/null 2>&1; then
    remote_ok "Postgres pg_isready passed inside db container"
  else
    remote_fail "Postgres pg_isready failed inside db container"
  fi

  if command -v curl >/dev/null 2>&1; then
    if local_health_payload="$(curl -fsS --connect-timeout 3 --max-time 10 "${API_LOCAL_HEALTH_URL}" 2>/dev/null)"; then
      if command -v python3 >/dev/null 2>&1; then
        if HEALTH_PAYLOAD="${local_health_payload}" python3 - <<'PY' >/dev/null 2>&1
import json
import os

payload = json.loads(os.environ["HEALTH_PAYLOAD"])
if payload.get("status") != "ok" or payload.get("database") != "online":
    raise SystemExit(1)
PY
        then
          remote_ok "localhost app health passed"
        else
          remote_fail "localhost app health returned an invalid payload"
        fi
      else
        remote_ok "localhost app health responded; python3 unavailable on host so payload shape was not validated"
      fi
    else
      remote_fail "localhost app health failed at ${API_LOCAL_HEALTH_URL}"
    fi
  else
    remote_warn "curl is not installed on host; localhost app health skipped"
  fi

  if command -v openssl >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then
    cert_end="$(
      {
        printf '' \
          | timeout 15 openssl s_client -servername "${API_TLS_HOST}" -connect 127.0.0.1:443 2>/dev/null \
          | openssl x509 -noout -enddate 2>/dev/null \
          | sed 's/^notAfter=//'
      } || true
    )"
    if [[ -z "${cert_end}" ]]; then
      remote_warn "nginx TLS expiry could not be read from 127.0.0.1:443"
    elif cert_epoch="$(date -d "${cert_end}" +%s 2>/dev/null)"; then
      now_epoch="$(date +%s)"
      days_left=$(( (cert_epoch - now_epoch) / 86400 ))
      if (( days_left < 0 )); then
        remote_fail "nginx TLS certificate is expired (${cert_end})"
      elif (( days_left < TLS_CRITICAL_DAYS )); then
        remote_fail "nginx TLS certificate expires in ${days_left} day(s) (${cert_end})"
      elif (( days_left < TLS_WARN_DAYS )); then
        remote_warn "nginx TLS certificate expires in ${days_left} day(s) (${cert_end})"
      else
        remote_ok "nginx TLS certificate has ${days_left} day(s) remaining"
      fi
    else
      remote_warn "nginx TLS expiry date could not be parsed: ${cert_end}"
    fi
  else
    remote_warn "openssl or timeout is unavailable on host; nginx TLS expiry skipped"
  fi

  if [[ "${CHECK_BACKUPS}" == "true" ]]; then
    if backup_output="$("${COMPOSE[@]}" exec -T app python3 - "${BACKUP_MAX_AGE_HOURS}" <<'PY'
import logging
import sys
from datetime import datetime, timezone

logging.disable(logging.CRITICAL)

try:
    from services.backup_service import backup_service
except Exception as exc:
    print(f"backup_check_status=error error_type={type(exc).__name__}")
    raise SystemExit(2)

try:
    max_age_hours = float(sys.argv[1])
except (IndexError, ValueError):
    print("backup_check_status=error error_type=InvalidMaxAge")
    raise SystemExit(2)

try:
    items = backup_service.list_backups(limit=100)
except Exception as exc:
    print(f"backup_check_status=error error_type={type(exc).__name__}")
    raise SystemExit(2)

now = datetime.now(timezone.utc)
failures = 0

for kind in ("db", "media"):
    latest = next((item for item in items if item.get("kind") == kind), None)
    if latest is None:
        print(f"backup_kind={kind} status=missing")
        failures += 1
        continue

    created_at = latest.get("created_at")
    if not isinstance(created_at, datetime):
        print(f"backup_kind={kind} status=invalid_created_at")
        failures += 1
        continue
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    age_hours = max(0.0, (now - created_at).total_seconds() / 3600)
    status = "fresh" if age_hours <= max_age_hours else "stale"
    name = str(latest.get("name") or "<unnamed>")
    if len(name) > 120:
        name = name[:117] + "..."

    print(
        f"backup_kind={kind} status={status} "
        f"age_hours={age_hours:.1f} created_at={created_at.isoformat()} name={name}"
    )
    if status != "fresh":
        failures += 1

print(f"backup_items_seen={len(items)} max_age_hours={max_age_hours:g}")
raise SystemExit(1 if failures else 0)
PY
)"; then
      print_prefixed backup "${backup_output}"
      remote_ok "backup freshness passed"
    else
      print_prefixed backup "${backup_output}"
      remote_fail "backup freshness failed"
    fi
  else
    remote_warn "backup freshness skipped because CHECK_BACKUPS=false"
  fi
fi

if (( remote_failures > 0 )); then
  remote_log summary "status=failed critical_failures=${remote_failures} warnings=${remote_warnings}"
  exit 1
fi

remote_log summary "status=passed critical_failures=0 warnings=${remote_warnings}"
REMOTE
  then
    ok "optional SSH host checks passed"
  else
    fail "optional SSH host checks failed"
  fi
}

if [[ "${SKIP_PUBLIC_CHECKS}" == "true" ]]; then
  log public "skipped (SKIP_PUBLIC_CHECKS=true)"
else
  run_public_checks
fi

if [[ "${PUBLIC_ONLY}" == "true" ]]; then
  log ssh "skipped (--public-only)"
elif [[ -n "${API_SSH_HOST}" && -n "${API_SSH_USER}" ]]; then
  run_ssh_checks
else
  log ssh "skipped (API_SSH_HOST/API_SSH_USER not set)"
fi

if (( critical_failures > 0 )); then
  log summary "status=failed critical_failures=${critical_failures} warnings=${warnings}"
  exit 1
fi

log summary "status=passed critical_failures=0 warnings=${warnings}"
