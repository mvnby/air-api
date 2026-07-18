#!/usr/bin/env bash
set -euo pipefail

WEB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WEB_ROOT"

if ! command -v rg >/dev/null 2>&1; then
  echo "Theme audit requires ripgrep (rg)." >&2
  exit 2
fi

echo "Theme hardcode audit (src)"
echo "Allowed token source: src/assets/index.css"

# Heuristics: likely light-theme hardcodes that break dark mode consistency.
# The global token file is the only place where canonical values may live.
if rg -n --hidden --glob 'src/**/*.{vue,astro,css,scss}' --glob '!src/assets/index.css' \
  'rgba\(255,\s*255,\s*255|rgba\(245,\s*253,\s*250|#fff\b|#ffffff\b|linear-gradient\([^)]*#0f8f8d[^)]*#3aa56e|linear-gradient\([^)]*#0a8e8c[^)]*#2b6eb3' \
  src; then
  echo "Theme hardcodes found. Replace them with --panel-* tokens." >&2
  exit 1
fi

echo "theme_audit=passed"
