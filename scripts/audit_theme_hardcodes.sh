#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Theme hardcode audit (web/src)"
echo "Allowed token source: web/src/assets/index.css"
echo

# Heuristics: likely light-theme hardcodes that break dark mode consistency.
# Exclude the global token file itself where canonical values live.
rg -n --hidden --glob 'web/src/**/*.{vue,astro,css,scss}' --glob '!web/src/assets/index.css' \
  'rgba\(255,\s*255,\s*255|rgba\(245,\s*253,\s*250|#fff\b|#ffffff\b|linear-gradient\([^)]*#0f8f8d[^)]*#3aa56e|linear-gradient\([^)]*#0a8e8c[^)]*#2b6eb3' \
  web/src || true
