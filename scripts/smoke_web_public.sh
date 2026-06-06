#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Read-only public storefront/API smoke.

Environment:
  BASE_URL        Storefront origin to check. Default: https://mvn.by
  API_ORIGIN_URL API origin to check. Default: https://api.mvn.by
  API_V1_URL     API v1 base. Default: $API_ORIGIN_URL/api/v1
  PRODUCT_PATH   Optional product path, for example /product/elb07pn/
  BRAND_PATH     Optional brand path, for example /brands/mdv/
  ASSET_PATH     Optional asset path, for example /_astro/index.hash.css
  BASIC_AUTH     Optional storefront basic auth as user:password.
  TIMEOUT_SECONDS curl max time per request. Default: 20

The script does not mutate manager/API/web state.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

BASE_URL="${BASE_URL:-https://mvn.by}"
API_ORIGIN_URL="${API_ORIGIN_URL:-https://api.mvn.by}"
API_V1_URL="${API_V1_URL:-${API_ORIGIN_URL%/}/api/v1}"
BASIC_AUTH="${BASIC_AUTH:-}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-20}"

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmpdir"
}
trap cleanup EXIT

trim_trailing_slash() {
  local value="$1"
  printf '%s' "${value%/}"
}

join_url() {
  local base path
  base="$(trim_trailing_slash "$1")"
  path="$2"
  if [[ "$path" != /* ]]; then
    path="/$path"
  fi
  printf '%s%s' "$base" "$path"
}

header_value() {
  local file="$1"
  local header="$2"
  awk -v key="$header" '
    BEGIN { IGNORECASE = 1 }
    index($0, key ":") == 1 {
      sub(/^[^:]+:[[:space:]]*/, "", $0)
      sub(/\r$/, "", $0)
      print
      exit
    }
  ' "$file"
}

fetch_url() {
  local label="$1"
  local url="$2"
  local auth_scope="${3:-public}"
  local body_file="$tmpdir/${label//[^A-Za-z0-9_]/_}.body"
  local headers_file="$tmpdir/${label//[^A-Za-z0-9_]/_}.headers"
  local status
  local curl_args=(
    --silent
    --show-error
    --location
    --max-time "$TIMEOUT_SECONDS"
    --dump-header "$headers_file"
    --output "$body_file"
    --write-out '%{http_code}'
  )

  if [[ "$auth_scope" == "storefront" && -n "$BASIC_AUTH" ]]; then
    curl_args+=(--user "$BASIC_AUTH")
  fi

  status="$(
    curl "${curl_args[@]}" "$url"
  )"

  if [[ ! "$status" =~ ^[23][0-9][0-9]$ ]]; then
    echo "FAIL $label: HTTP $status $url" >&2
    echo "Headers:" >&2
    sed -n '1,40p' "$headers_file" >&2 || true
    return 1
  fi

  local cache_control cf_cache_status x_robots
  cache_control="$(header_value "$headers_file" "cache-control" || true)"
  cf_cache_status="$(header_value "$headers_file" "cf-cache-status" || true)"
  x_robots="$(header_value "$headers_file" "x-robots-tag" || true)"

  printf 'OK   %-18s HTTP %s %s\n' "$label" "$status" "$url"
  [[ -n "$cache_control" ]] && printf '     cache-control: %s\n' "$cache_control"
  [[ -n "$cf_cache_status" ]] && printf '     cf-cache-status: %s\n' "$cf_cache_status"
  [[ -n "$x_robots" ]] && printf '     x-robots-tag: %s\n' "$x_robots"

  LAST_BODY_FILE="$body_file"
}

extract_first_product_path() {
  local file="$1"
  python3 - "$file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)

for item in data.get("items") or []:
    slug = item.get("slug")
    if slug:
        print(f"/product/{slug}/")
        raise SystemExit(0)

raise SystemExit("No product slug found in API catalog response")
PY
}

extract_first_brand_path() {
  local file="$1"
  python3 - "$file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)

for item in data or []:
    slug = item.get("slug")
    if slug:
        print(f"/brands/{slug}/")
        raise SystemExit(0)

raise SystemExit("No brand slug found in API brand response")
PY
}

extract_first_asset_path() {
  local file="$1"
  python3 - "$file" <<'PY'
import re
import sys

html = open(sys.argv[1], "r", encoding="utf-8", errors="ignore").read()
match = re.search(r'''(?:href|src)=["']([^"']*/_astro/[^"']+)["']''', html)
if not match:
    raise SystemExit("No /_astro asset reference found on home page")

value = match.group(1)
if value.startswith("http://") or value.startswith("https://"):
    print(value)
else:
    print(value if value.startswith("/") else f"/{value}")
PY
}

echo "Storefront smoke: $(trim_trailing_slash "$BASE_URL")"
echo "API smoke: $(trim_trailing_slash "$API_ORIGIN_URL")"

fetch_url "home" "$(join_url "$BASE_URL" "/")" "storefront"
home_body="$LAST_BODY_FILE"

fetch_url "catalog" "$(join_url "$BASE_URL" "/catalog/")" "storefront"
fetch_url "brands" "$(join_url "$BASE_URL" "/brands/")" "storefront"

fetch_url "api-health" "$(join_url "$API_ORIGIN_URL" "/api/health")"
fetch_url "api-products" "$(join_url "$API_V1_URL" "/catalog?limit=5")"
catalog_body="$LAST_BODY_FILE"
fetch_url "api-filters" "$(join_url "$API_V1_URL" "/filters/config")"

product_path="${PRODUCT_PATH:-}"
if [[ -z "$product_path" ]]; then
  product_path="$(extract_first_product_path "$catalog_body")"
fi
fetch_url "product" "$(join_url "$BASE_URL" "$product_path")" "storefront"

brand_path="${BRAND_PATH:-}"
if [[ -z "$brand_path" ]]; then
  fetch_url "api-brands" "$(join_url "$API_V1_URL" "/content/brands")"
  brand_path="$(extract_first_brand_path "$LAST_BODY_FILE")"
fi
fetch_url "brand-page" "$(join_url "$BASE_URL" "$brand_path")" "storefront"

asset_path="${ASSET_PATH:-}"
if [[ -z "$asset_path" ]]; then
  asset_path="$(extract_first_asset_path "$home_body")"
fi

if [[ "$asset_path" == http://* || "$asset_path" == https://* ]]; then
  fetch_url "asset" "$asset_path" "storefront"
else
  fetch_url "asset" "$(join_url "$BASE_URL" "$asset_path")" "storefront"
fi

echo "Public storefront/API smoke passed."
