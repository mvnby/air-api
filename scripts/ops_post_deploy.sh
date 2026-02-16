#!/usr/bin/env bash
set -euo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml"
PROJECT_DIR="/opt/air-api"

RUN_NORMALIZE_LEGACY="${RUN_NORMALIZE_LEGACY:-true}"
HIDE_LEGACY_GROUPS="${HIDE_LEGACY_GROUPS:-area}"
RUN_REPORT_LEGACY_LINKS="${RUN_REPORT_LEGACY_LINKS:-true}"
RUN_CLEANUP_LEGACY_LINKS="${RUN_CLEANUP_LEGACY_LINKS:-false}"
RUN_POST_DEPLOY_OPS="${RUN_POST_DEPLOY_OPS:-false}"

echo "=== Post-Deploy Ops: start ==="
echo "RUN_POST_DEPLOY_OPS=${RUN_POST_DEPLOY_OPS}"
echo "RUN_NORMALIZE_LEGACY=${RUN_NORMALIZE_LEGACY}"
echo "HIDE_LEGACY_GROUPS=${HIDE_LEGACY_GROUPS}"
echo "RUN_REPORT_LEGACY_LINKS=${RUN_REPORT_LEGACY_LINKS}"
echo "RUN_CLEANUP_LEGACY_LINKS=${RUN_CLEANUP_LEGACY_LINKS}"

if [[ "${RUN_POST_DEPLOY_OPS}" != "true" ]]; then
  echo "[ops] RUN_POST_DEPLOY_OPS is not true, skipping."
  exit 0
fi

cd "${PROJECT_DIR}"

run_in_app() {
  ${COMPOSE} exec -T app sh -lc "$1"
}

script_exists() {
  run_in_app "test -f $1"
}

echo "[ops] Ensuring app is running..."
${COMPOSE} up -d app >/dev/null

if [[ "${RUN_NORMALIZE_LEGACY}" == "true" ]]; then
  if script_exists "scripts/normalize_legacy.py"; then
    echo "[ops] Running normalize_legacy.py"
    run_in_app "python3 scripts/normalize_legacy.py"
  else
    echo "[ops] Skip normalize: scripts/normalize_legacy.py not found in image"
  fi
fi

if [[ -n "${HIDE_LEGACY_GROUPS}" ]]; then
  if script_exists "scripts/hide_legacy_tag_groups.py"; then
    echo "[ops] Hiding legacy groups: ${HIDE_LEGACY_GROUPS}"
    run_in_app "python3 scripts/hide_legacy_tag_groups.py --groups ${HIDE_LEGACY_GROUPS}"
  else
    echo "[ops] Skip hide groups: scripts/hide_legacy_tag_groups.py not found in image"
  fi
fi

if [[ "${RUN_REPORT_LEGACY_LINKS}" == "true" ]]; then
  if script_exists "scripts/report_legacy_tag_links.py"; then
    echo "[ops] Report legacy links"
    run_in_app "python3 scripts/report_legacy_tag_links.py"
  else
    echo "[ops] Skip report: scripts/report_legacy_tag_links.py not found in image"
  fi
fi

if [[ "${RUN_CLEANUP_LEGACY_LINKS}" == "true" ]]; then
  if script_exists "scripts/cleanup_legacy_tag_links.py"; then
    echo "[ops] Cleanup legacy links (execute=true)"
    run_in_app "python3 scripts/cleanup_legacy_tag_links.py --execute"
  else
    echo "[ops] Skip cleanup: scripts/cleanup_legacy_tag_links.py not found in image"
  fi
fi

echo "=== Post-Deploy Ops: done ==="
