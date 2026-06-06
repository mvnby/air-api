#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Roll back only the protected production shadow Astro runtime.

Environment:
  DRY_RUN                    true by default; set false to mutate VPS state.
  WEB_RUNTIME_DIR            Repo checkout on the web VPS. Default: /opt/air-api
  COMPOSE_FILE               Compose file path relative to WEB_RUNTIME_DIR.
                             Default: docker-compose.web.yml
  WEB_SHADOW_SERVICE         Compose service. Default: web-public-shadow
  DISABLE_NGINX_SHADOW       Remove the enabled shadow nginx symlink. Default: false
  NGINX_SHADOW_ENABLED_PATH  Default: /etc/nginx/sites-enabled/mvn-web-shadow.conf
  RUN_PUBLIC_STATIC_SMOKE    Run public static mvn.by smoke. Default: true
  PUBLIC_STATIC_BASE_URL     Public static URL. Default: https://mvn.by
  API_ORIGIN_URL             API origin URL. Default: https://api.mvn.by

This rollback does not delete static releases, does not alter DNS/Cloudflare,
and does not touch the legacy mvn-web fallback. It stops only the shadow service
and optionally disables the protected shadow nginx host.
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

DRY_RUN="${DRY_RUN:-true}"
WEB_RUNTIME_DIR="${WEB_RUNTIME_DIR:-/opt/air-api}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.web.yml}"
WEB_SHADOW_SERVICE="${WEB_SHADOW_SERVICE:-web-public-shadow}"
DISABLE_NGINX_SHADOW="${DISABLE_NGINX_SHADOW:-false}"
NGINX_SHADOW_ENABLED_PATH="${NGINX_SHADOW_ENABLED_PATH:-/etc/nginx/sites-enabled/mvn-web-shadow.conf}"
RUN_PUBLIC_STATIC_SMOKE="${RUN_PUBLIC_STATIC_SMOKE:-true}"
PUBLIC_STATIC_BASE_URL="${PUBLIC_STATIC_BASE_URL:-https://mvn.by}"
API_ORIGIN_URL="${API_ORIGIN_URL:-https://api.mvn.by}"
API_V1_URL="${API_V1_URL:-${API_ORIGIN_URL%/}/api/v1}"

echo "Shadow runtime rollback"
echo "- dry_run: $DRY_RUN"
echo "- runtime_dir: $WEB_RUNTIME_DIR"
echo "- service: $WEB_SHADOW_SERVICE"
echo "- disable_nginx_shadow: $DISABLE_NGINX_SHADOW"

if [[ ! -d "$WEB_RUNTIME_DIR" ]]; then
  echo "WEB_RUNTIME_DIR does not exist: $WEB_RUNTIME_DIR" >&2
  exit 1
fi

cd "$WEB_RUNTIME_DIR"

run_cmd docker compose -f "$COMPOSE_FILE" stop "$WEB_SHADOW_SERVICE"

if is_truthy "$DISABLE_NGINX_SHADOW"; then
  run_cmd sudo rm -f "$NGINX_SHADOW_ENABLED_PATH"
  run_cmd sudo nginx -t
  run_cmd sudo systemctl reload nginx
fi

if is_truthy "$RUN_PUBLIC_STATIC_SMOKE"; then
  run_cmd env \
    BASE_URL="$PUBLIC_STATIC_BASE_URL" \
    API_ORIGIN_URL="$API_ORIGIN_URL" \
    API_V1_URL="$API_V1_URL" \
    bash scripts/smoke_web_public.sh
fi

echo "Shadow runtime rollback completed."
