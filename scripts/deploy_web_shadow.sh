#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Deploy the protected production shadow Astro runtime on the web VPS.

Required:
  DEPLOY_SHA                 Git commit SHA to fetch and build.

Environment:
  DRY_RUN                    true by default; set false to mutate VPS state.
  WEB_RUNTIME_DIR            Repo checkout on the web VPS. Default: /opt/air-api
  COMPOSE_FILE               Compose file path relative to WEB_RUNTIME_DIR.
                             Default: docker-compose.web.yml
  WEB_SHADOW_SERVICE         Compose service. Default: web-public-shadow
  WEB_SHADOW_PORT            Localhost bind port. Default: 4322
  WEB_SHADOW_BASE_PATH       Runtime base path. Default: /
  WEB_SHADOW_INTERNAL_API_URL
                             Build/runtime API v1 URL. Default: https://api.mvn.by/api/v1
  WEB_SHADOW_PUBLIC_API_URL  Browser API v1 URL. Default: https://api.mvn.by/api/v1
  WEB_SHADOW_PUBLIC_SITE_URL Site URL used by Astro. Default: https://mvn.by
  WEB_SHADOW_PUBLIC_GTM_ID   Optional GTM id.
  WEB_SHADOW_RUNTIME_FRESHNESS
                             Default: true
  RUN_LOCAL_SMOKE            Run localhost runtime smoke. Default: true
  RUN_SHADOW_HOST_SMOKE      Run protected nginx host smoke. Default: false
  RUN_PUBLIC_STATIC_SMOKE    Run public static mvn.by smoke. Default: true
  SHADOW_PUBLIC_BASE_URL     Protected host smoke base URL. Default: http://127.0.0.1
  SHADOW_HOST_HEADER         Host header for origin-only smoke. Default: shadow-web.mvn.by
  SHADOW_BASIC_AUTH          Basic auth user:password for protected host smoke.
  PUBLIC_STATIC_BASE_URL     Public static URL. Default: https://mvn.by
  WEB_SHADOW_DEPLOY_RECORD   Deploy record file. Default: .web-public-shadow-deploy

This script does not edit DNS, Cloudflare, public mvn.by nginx routing, or static
release directories. It only fetches the requested SHA, builds/starts the shadow
compose service, records the SHA, and runs requested read-only smokes.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

is_truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

print_cmd() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
}

run_cmd() {
  print_cmd "$@"
  if ! is_truthy "$DRY_RUN"; then
    "$@"
  fi
}

normalize_base_path() {
  local value="${1:-/}"
  value="/${value#/}"
  value="${value%/}"
  if [[ -z "$value" ]]; then
    value="/"
  fi
  printf '%s' "$value"
}

DRY_RUN="${DRY_RUN:-true}"
DEPLOY_SHA="${DEPLOY_SHA:-}"
WEB_RUNTIME_DIR="${WEB_RUNTIME_DIR:-/opt/air-api}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.web.yml}"
WEB_SHADOW_SERVICE="${WEB_SHADOW_SERVICE:-web-public-shadow}"
WEB_SHADOW_PORT="${WEB_SHADOW_PORT:-4322}"
WEB_SHADOW_BASE_PATH="$(normalize_base_path "${WEB_SHADOW_BASE_PATH:-/}")"
WEB_SHADOW_INTERNAL_API_URL="${WEB_SHADOW_INTERNAL_API_URL:-https://api.mvn.by/api/v1}"
WEB_SHADOW_PUBLIC_API_URL="${WEB_SHADOW_PUBLIC_API_URL:-https://api.mvn.by/api/v1}"
WEB_SHADOW_PUBLIC_SITE_URL="${WEB_SHADOW_PUBLIC_SITE_URL:-https://mvn.by}"
WEB_SHADOW_PUBLIC_GTM_ID="${WEB_SHADOW_PUBLIC_GTM_ID:-}"
WEB_SHADOW_RUNTIME_FRESHNESS="${WEB_SHADOW_RUNTIME_FRESHNESS:-true}"
RUN_LOCAL_SMOKE="${RUN_LOCAL_SMOKE:-true}"
RUN_SHADOW_HOST_SMOKE="${RUN_SHADOW_HOST_SMOKE:-false}"
RUN_PUBLIC_STATIC_SMOKE="${RUN_PUBLIC_STATIC_SMOKE:-true}"
SHADOW_PUBLIC_BASE_URL="${SHADOW_PUBLIC_BASE_URL:-http://127.0.0.1}"
SHADOW_HOST_HEADER="${SHADOW_HOST_HEADER:-shadow-web.mvn.by}"
SHADOW_BASIC_AUTH="${SHADOW_BASIC_AUTH:-}"
PUBLIC_STATIC_BASE_URL="${PUBLIC_STATIC_BASE_URL:-https://mvn.by}"
WEB_SHADOW_DEPLOY_RECORD="${WEB_SHADOW_DEPLOY_RECORD:-.web-public-shadow-deploy}"

if [[ ! "$DEPLOY_SHA" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
  echo "DEPLOY_SHA must be a 7-40 character git commit SHA." >&2
  exit 1
fi

echo "Shadow runtime deploy"
echo "- dry_run: $DRY_RUN"
echo "- deploy_sha: $DEPLOY_SHA"
echo "- runtime_dir: $WEB_RUNTIME_DIR"
echo "- service: $WEB_SHADOW_SERVICE"
echo "- localhost: 127.0.0.1:$WEB_SHADOW_PORT"
echo "- base_path: $WEB_SHADOW_BASE_PATH"

if [[ ! -e "$WEB_RUNTIME_DIR/.git" ]]; then
  echo "WEB_RUNTIME_DIR is not a git checkout: $WEB_RUNTIME_DIR" >&2
  exit 1
fi

cd "$WEB_RUNTIME_DIR"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "WEB_RUNTIME_DIR is not inside a git work tree: $WEB_RUNTIME_DIR" >&2
  exit 1
fi

if ! is_truthy "$DRY_RUN"; then
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Refusing to deploy from a dirty checkout in $WEB_RUNTIME_DIR." >&2
    exit 1
  fi
fi

run_cmd git fetch --no-tags origin "$DEPLOY_SHA"
run_cmd git checkout --detach "$DEPLOY_SHA"

if ! is_truthy "$DRY_RUN"; then
  checked_out_sha="$(git rev-parse HEAD)"
  requested_sha="$(git rev-parse "$DEPLOY_SHA^{commit}")"
  if [[ "$checked_out_sha" != "$requested_sha" ]]; then
    echo "Checked out $checked_out_sha, expected $requested_sha." >&2
    exit 1
  fi
fi

export WEB_SHADOW_INTERNAL_API_URL
export WEB_SHADOW_PUBLIC_API_URL
export WEB_SHADOW_PUBLIC_SITE_URL
export WEB_SHADOW_PUBLIC_GTM_ID
export WEB_SHADOW_RUNTIME_FRESHNESS
export WEB_SHADOW_PORT
export WEB_SHADOW_BASE_PATH

run_cmd docker compose -f "$COMPOSE_FILE" build "$WEB_SHADOW_SERVICE"
run_cmd docker compose -f "$COMPOSE_FILE" up -d --no-deps "$WEB_SHADOW_SERVICE"
run_cmd docker compose -f "$COMPOSE_FILE" ps "$WEB_SHADOW_SERVICE"

if is_truthy "$DRY_RUN"; then
  print_cmd bash -c "printf '%s\n' deploy_sha=$DEPLOY_SHA service=$WEB_SHADOW_SERVICE port=$WEB_SHADOW_PORT > $WEB_SHADOW_DEPLOY_RECORD"
else
  {
    printf 'deployed_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'deploy_sha=%s\n' "$(git rev-parse HEAD)"
    printf 'service=%s\n' "$WEB_SHADOW_SERVICE"
    printf 'port=%s\n' "$WEB_SHADOW_PORT"
    printf 'base_path=%s\n' "$WEB_SHADOW_BASE_PATH"
  } > "$WEB_SHADOW_DEPLOY_RECORD"
fi

local_base_url="http://127.0.0.1:${WEB_SHADOW_PORT}"
if [[ "$WEB_SHADOW_BASE_PATH" != "/" ]]; then
  local_base_url="${local_base_url}${WEB_SHADOW_BASE_PATH}"
fi

if is_truthy "$RUN_LOCAL_SMOKE"; then
  run_cmd env \
    BASE_URL="$local_base_url" \
    API_ORIGIN_URL="${WEB_SHADOW_PUBLIC_API_URL%/api/v1}" \
    API_V1_URL="$WEB_SHADOW_PUBLIC_API_URL" \
    REQUIRE_SSR_HEADERS=true \
    bash scripts/smoke_web_public.sh
fi

if is_truthy "$RUN_SHADOW_HOST_SMOKE"; then
  if [[ -z "$SHADOW_BASIC_AUTH" ]]; then
    echo "RUN_SHADOW_HOST_SMOKE requires SHADOW_BASIC_AUTH=user:password." >&2
    exit 1
  fi
  print_cmd env \
    BASE_URL="$SHADOW_PUBLIC_BASE_URL" \
    HOST_HEADER="$SHADOW_HOST_HEADER" \
    BASIC_AUTH="[redacted]" \
    API_ORIGIN_URL="${WEB_SHADOW_PUBLIC_API_URL%/api/v1}" \
    API_V1_URL="$WEB_SHADOW_PUBLIC_API_URL" \
    REQUIRE_NOINDEX=true \
    REQUIRE_NO_STORE=true \
    REQUIRE_SSR_HEADERS=true \
    bash scripts/smoke_web_public.sh
  if ! is_truthy "$DRY_RUN"; then
    env \
      BASE_URL="$SHADOW_PUBLIC_BASE_URL" \
      HOST_HEADER="$SHADOW_HOST_HEADER" \
      BASIC_AUTH="$SHADOW_BASIC_AUTH" \
      API_ORIGIN_URL="${WEB_SHADOW_PUBLIC_API_URL%/api/v1}" \
      API_V1_URL="$WEB_SHADOW_PUBLIC_API_URL" \
      REQUIRE_NOINDEX=true \
      REQUIRE_NO_STORE=true \
      REQUIRE_SSR_HEADERS=true \
      bash scripts/smoke_web_public.sh
  fi
fi

if is_truthy "$RUN_PUBLIC_STATIC_SMOKE"; then
  run_cmd env \
    BASE_URL="$PUBLIC_STATIC_BASE_URL" \
    API_ORIGIN_URL="${WEB_SHADOW_PUBLIC_API_URL%/api/v1}" \
    API_V1_URL="$WEB_SHADOW_PUBLIC_API_URL" \
    bash scripts/smoke_web_public.sh
fi

echo "Shadow runtime deploy completed."
