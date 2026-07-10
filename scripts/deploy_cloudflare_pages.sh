#!/usr/bin/env bash
set -euo pipefail

DIST_DIR="${PAGES_DIST_DIR:-web/dist}"
PROJECT_NAME="${CLOUDFLARE_PAGES_PROJECT:-mvn-by}"
DEPLOY_BRANCH="${CLOUDFLARE_PAGES_BRANCH:-}"
COMMIT_SHA="${PAGES_COMMIT_SHA:-}"
WRANGLER_VERSION="${WRANGLER_VERSION:-4.110.0}"
WRANGLER_BIN="${WRANGLER_BIN:-npx}"
WRANGLER_RUNNER="${WRANGLER_RUNNER:-npx}"
SMOKE_ATTEMPTS="${PAGES_SMOKE_ATTEMPTS:-20}"
SMOKE_DELAY_SECONDS="${PAGES_SMOKE_DELAY_SECONDS:-3}"
OUTPUT_FILE="${PAGES_DEPLOY_OUTPUT_FILE:-/tmp/cloudflare-pages-deploy.log}"

log() {
  printf '[pages-deploy][%s] %s\n' "$1" "$2"
}

[[ -n "${CLOUDFLARE_API_TOKEN:-}" ]] || {
  log error "CLOUDFLARE_API_TOKEN is required"
  exit 1
}
[[ -n "${CLOUDFLARE_ACCOUNT_ID:-}" ]] || {
  log error "CLOUDFLARE_ACCOUNT_ID is required"
  exit 1
}
[[ "${PROJECT_NAME}" =~ ^[a-z0-9][a-z0-9-]{0,57}[a-z0-9]$ ]] || {
  log error "invalid Cloudflare Pages project name: ${PROJECT_NAME}"
  exit 1
}
[[ "${DEPLOY_BRANCH}" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,80}$ ]] || {
  log error "invalid Pages branch: ${DEPLOY_BRANCH}"
  exit 1
}
[[ "${COMMIT_SHA}" =~ ^[0-9a-f]{40}$ ]] || {
  log error "PAGES_COMMIT_SHA must be a full Git SHA"
  exit 1
}
[[ -s "${DIST_DIR}/index.html" ]] || {
  log error "Pages dist is missing index.html: ${DIST_DIR}"
  exit 1
}
python3 - "${DIST_DIR}/release.json" "${COMMIT_SHA}" <<'PY'
import json
import sys
from pathlib import Path

release = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if release != {"sha": sys.argv[2]}:
    raise SystemExit("release.json does not match PAGES_COMMIT_SHA")
PY
for command in "${WRANGLER_BIN}" python3 curl; do
  command -v "${command}" >/dev/null 2>&1 || {
    log error "required command is missing: ${command}"
    exit 1
  }
done

case "${WRANGLER_RUNNER}" in
  npx) wrangler_command=("${WRANGLER_BIN}" --yes "wrangler@${WRANGLER_VERSION}") ;;
  pnpm) wrangler_command=("${WRANGLER_BIN}" dlx "wrangler@${WRANGLER_VERSION}") ;;
  *)
    log error "WRANGLER_RUNNER must be npx or pnpm"
    exit 1
    ;;
esac

"${wrangler_command[@]}" pages deploy "${DIST_DIR}" \
  --project-name "${PROJECT_NAME}" \
  --branch "${DEPLOY_BRANCH}" \
  --commit-hash "${COMMIT_SHA}" \
  --commit-message "MVN ${COMMIT_SHA}" \
  --commit-dirty=false \
  2>&1 | tee "${OUTPUT_FILE}"

deployment_url="$(python3 - "${OUTPUT_FILE}" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
urls = re.findall(r"https://[a-zA-Z0-9.-]+\.pages\.dev", text)
if not urls:
    raise SystemExit("Wrangler output did not contain a pages.dev deployment URL")
print(urls[-1].rstrip("."))
PY
)"

for attempt in $(seq 1 "${SMOKE_ATTEMPTS}"); do
  if curl -fsSL --retry 2 --retry-delay 1 "${deployment_url}/" >/dev/null \
    && curl -fsSL --retry 2 --retry-delay 1 "${deployment_url}/catalog/" >/dev/null \
    && remote_sha="$(curl -fsSL --retry 2 --retry-delay 1 \
      "${deployment_url}/release.json?sha=${COMMIT_SHA}" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])')" \
    && [[ "${remote_sha}" == "${COMMIT_SHA}" ]]; then
    log smoke "deployment is ready on attempt ${attempt}: ${deployment_url}"
    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
      printf 'deployment_url=%s\n' "${deployment_url}" >> "${GITHUB_OUTPUT}"
    fi
    log "done" "Pages branch ${DEPLOY_BRANCH} deployed"
    exit 0
  fi
  sleep "${SMOKE_DELAY_SECONDS}"
done

log error "Pages deployment failed smoke checks: ${deployment_url}"
exit 1
