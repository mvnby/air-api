#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to extract OpenAPI schema" >&2
  exit 1
fi

python3 scripts/legacy/extract_openapi.py
if command -v npm >/dev/null 2>&1; then
  (cd manager_frontend && npm run gen:api)
elif [[ -x "$REPO_ROOT/manager_frontend/node_modules/.bin/openapi" ]]; then
  (
    cd manager_frontend
    PATH="$PWD/node_modules/.bin:$PATH" openapi \
      --input ../openapi.json \
      --output ./src/client \
      --client fetch \
      --useUnionTypes
  )
else
  echo "npm or manager_frontend/node_modules/.bin/openapi is required to generate manager API client" >&2
  exit 1
fi
