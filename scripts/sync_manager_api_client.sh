#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to extract OpenAPI schema" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to generate manager API client" >&2
  exit 1
fi

python3 scripts/legacy/extract_openapi.py
(cd manager_frontend && npm run gen:api)

