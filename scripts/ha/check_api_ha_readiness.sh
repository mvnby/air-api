#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}" || exit 1

HA_READINESS_STRICT="${HA_READINESS_STRICT:-false}"

API_HOST="${API_HOST:-api.mvn.by}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://${API_HOST}}"
PRIMARY_ORIGIN="${PRIMARY_ORIGIN:-185.250.45.54}"
STANDBY_ORIGIN="${STANDBY_ORIGIN:-193.47.42.213}"

PRIMARY_SSH="${PRIMARY_SSH:-mvn-api}"
STANDBY_SSH="${STANDBY_SSH:-zakup}"
PRIMARY_PROJECT_DIR="${PRIMARY_PROJECT_DIR:-${API_PROJECT_DIR:-/opt/air-api}}"
PRIMARY_COMPOSE_FILE="${PRIMARY_COMPOSE_FILE:-${API_COMPOSE_FILE:-docker-compose.prod.yml}}"
STANDBY_PROJECT_DIR="${STANDBY_PROJECT_DIR:-${API_STANDBY_PROJECT_DIR:-/opt/mvn-reserve}}"
STANDBY_COMPOSE_FILE="${STANDBY_COMPOSE_FILE:-${API_STANDBY_COMPOSE_FILE:-docker-compose.reserve.yml}}"

EXPECTED_CDN_BASE="${EXPECTED_CDN_BASE:-https://cdn.mvn.by}"
MIN_DB_CDN_URLS="${MIN_DB_CDN_URLS:-3}"

CHECK_ACTIVE_PASSIVE="${CHECK_ACTIVE_PASSIVE:-true}"
CHECK_POSTGRES_REPLICATION="${CHECK_POSTGRES_REPLICATION:-true}"
CHECK_MEDIA_CDN_DB="${CHECK_MEDIA_CDN_DB:-true}"
CHECK_POSTGRES_PITR="${CHECK_POSTGRES_PITR:-true}"
CHECK_CLOUDFLARE_LB="${CHECK_CLOUDFLARE_LB:-true}"

failures=0
warnings=0
soft_blockers=0

log() {
  local level="$1"
  shift
  printf '[ha-readiness][%s] %s\n' "${level}" "$*"
}

is_true() {
  case "${1:-}" in
    true|TRUE|True|1|yes|YES|Yes|on|ON|On) return 0 ;;
    *) return 1 ;;
  esac
}

quote_remote() {
  printf '%q' "$1"
}

fail() {
  failures=$((failures + 1))
  log fail "$*"
}

warn() {
  warnings=$((warnings + 1))
  log warn "$*"
}

soft_blocker() {
  if is_true "${HA_READINESS_STRICT}"; then
    fail "$*"
  else
    soft_blockers=$((soft_blockers + 1))
    log soft-blocker "$*"
  fi
}

run_required() {
  local name="$1"
  shift
  log start "${name}"
  if "$@"; then
    log ok "${name}"
  else
    fail "${name}"
  fi
}

run_required_shell() {
  local name="$1"
  shift
  log start "${name}"
  if bash -lc "$*"; then
    log ok "${name}"
  else
    fail "${name}"
  fi
}

run_active_passive() {
  API_HOST="${API_HOST}" \
    PUBLIC_BASE_URL="${PUBLIC_BASE_URL}" \
    PRIMARY_ORIGIN="${PRIMARY_ORIGIN}" \
    STANDBY_ORIGIN="${STANDBY_ORIGIN}" \
    PRIMARY_ROLE=primary \
    STANDBY_ROLE=standby \
    CHECK_PUBLIC_READY="${CHECK_PUBLIC_READY:-false}" \
    bash scripts/ha/check_active_passive.sh
}

run_postgres_replication() {
  PRIMARY_SSH="${PRIMARY_SSH}" \
    STANDBY_SSH="${STANDBY_SSH}" \
    PRIMARY_PROJECT_DIR="${PRIMARY_PROJECT_DIR}" \
    PRIMARY_COMPOSE_FILE="${PRIMARY_COMPOSE_FILE}" \
    STANDBY_PROJECT_DIR="${STANDBY_PROJECT_DIR}" \
    STANDBY_COMPOSE_FILE="${STANDBY_COMPOSE_FILE}" \
    bash scripts/ha/check_postgres_replication.sh
}

run_media_cdn_db() {
  local remote_cmd
  remote_cmd="cd $(quote_remote "${PRIMARY_PROJECT_DIR}") && active_service=app && if [ -f .active-api-slot ]; then active_slot=\$(tr -d '\\r\\n' < .active-api-slot); case \"\${active_slot}\" in blue|green) active_service=app-\${active_slot} ;; *) echo invalid active API slot >&2; exit 1 ;; esac; fi && docker compose -f $(quote_remote "${PRIMARY_COMPOSE_FILE}") --profile bluegreen exec -T \"\${active_service}\" python3 scripts/check_media_cdn_db_urls.py --expected-cdn-base $(quote_remote "${EXPECTED_CDN_BASE}") --min-db-cdn-urls $(quote_remote "${MIN_DB_CDN_URLS}") --max-fetches 10"
  # shellcheck disable=SC2029,SC2086
  ssh ${SSH_OPTS:-} "${PRIMARY_SSH}" "${remote_cmd}"
}

run_postgres_pitr() {
  local pitr_required="${POSTGRES_PITR_REQUIRED:-false}"
  if is_true "${HA_READINESS_STRICT}"; then
    pitr_required=true
  elif ! is_true "${pitr_required}"; then
    soft_blocker "POSTGRES_PITR_REQUIRED is not true; PITR is monitored in soft mode only"
  fi

  local remote_cmd
  remote_cmd="PROJECT_DIR=$(quote_remote "${PRIMARY_PROJECT_DIR}") COMPOSE_FILE=$(quote_remote "${PRIMARY_COMPOSE_FILE}") PITR_REQUIRED=$(quote_remote "${pitr_required}") /usr/local/sbin/mvn-postgres-pitr-status"
  # shellcheck disable=SC2029,SC2086
  ssh ${SSH_OPTS:-} "${PRIMARY_SSH}" "${remote_cmd}"
}

run_cloudflare_lb() {
  local missing=()
  local cloudflare_lb_token="${CLOUDFLARE_API_TOKEN_LB_AUDIT:-${CLOUDFLARE_LB_READ_TOKEN:-${CLOUDFLARE_API_TOKEN:-}}}"
  [[ -n "${cloudflare_lb_token}" ]] || missing+=("one of CLOUDFLARE_API_TOKEN_LB_AUDIT/CLOUDFLARE_LB_READ_TOKEN/CLOUDFLARE_API_TOKEN")
  [[ -n "${CLOUDFLARE_ZONE_ID:-}" ]] || missing+=("CLOUDFLARE_ZONE_ID")
  [[ -n "${CLOUDFLARE_ACCOUNT_ID:-}" ]] || missing+=("CLOUDFLARE_ACCOUNT_ID")
  if (( ${#missing[@]} > 0 )); then
    soft_blocker "Cloudflare LB config audit missing credentials: ${missing[*]}"
  fi

  if is_true "${HA_READINESS_STRICT}"; then
    export CF_LB_SKIP_IF_MISSING_CREDENTIALS=false
  else
    export CF_LB_SKIP_IF_MISSING_CREDENTIALS=true
  fi

  CF_LB_HOSTNAME="${CF_LB_HOSTNAME:-${API_HOST}}" \
    CF_LB_PRIMARY_ORIGIN="${CF_LB_PRIMARY_ORIGIN:-${PRIMARY_ORIGIN}}" \
    CF_LB_STANDBY_ORIGIN="${CF_LB_STANDBY_ORIGIN:-${STANDBY_ORIGIN}}" \
    CF_LB_HOST_HEADER="${CF_LB_HOST_HEADER:-${API_HOST}}" \
    CF_LB_MONITOR_PATH="${CF_LB_MONITOR_PATH:-/api/ready}" \
    CF_LB_MONITOR_METHOD="${CF_LB_MONITOR_METHOD:-GET}" \
    CF_LB_MONITOR_EXPECTED_CODE="${CF_LB_MONITOR_EXPECTED_CODE:-200}" \
    CF_LB_REQUIRE_ADAPTIVE_FAILOVER="${CF_LB_REQUIRE_ADAPTIVE_FAILOVER:-true}" \
    CF_LB_REQUIRE_SESSION_AFFINITY_OFF="${CF_LB_REQUIRE_SESSION_AFFINITY_OFF:-true}" \
    python3 scripts/ha/check_cloudflare_lb_config.py
}

log info "strict=${HA_READINESS_STRICT} primary=${PRIMARY_ORIGIN} standby=${STANDBY_ORIGIN} primary_ssh=${PRIMARY_SSH} standby_ssh=${STANDBY_SSH}"

if is_true "${CHECK_ACTIVE_PASSIVE}"; then
  run_required "active_passive_invariant" run_active_passive
else
  warn "active/passive check skipped"
fi

if is_true "${CHECK_POSTGRES_REPLICATION}"; then
  run_required "postgres_replication" run_postgres_replication
else
  warn "PostgreSQL replication check skipped"
fi

if is_true "${CHECK_MEDIA_CDN_DB}"; then
  run_required "db_backed_media_cdn" run_media_cdn_db
else
  warn "DB-backed media CDN check skipped"
fi

if is_true "${CHECK_POSTGRES_PITR}"; then
  run_required "postgres_pitr_status" run_postgres_pitr
else
  warn "PostgreSQL PITR check skipped"
fi

if is_true "${CHECK_CLOUDFLARE_LB}"; then
  run_required "cloudflare_lb_config" run_cloudflare_lb
else
  warn "Cloudflare LB config check skipped"
fi

if (( failures > 0 )); then
  log summary "status=failed failures=${failures} warnings=${warnings} soft_blockers=${soft_blockers}"
  exit 1
fi

log summary "status=passed failures=0 warnings=${warnings} soft_blockers=${soft_blockers}"
