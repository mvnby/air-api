#!/usr/bin/env bash
set -euo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml"
PROJECT_DIR="/opt/air-api"
OPS_SUMMARY_FILE="${OPS_SUMMARY_FILE:-/tmp/ops_summary.txt}"

OPS_MODE="${OPS_MODE:-report_only}" # report_only | normalize_report | full
RUN_NORMALIZE_LEGACY="${RUN_NORMALIZE_LEGACY:-false}"
RUN_BACKFILL_BRAND_SERIES="${RUN_BACKFILL_BRAND_SERIES:-false}"
RUN_SAFE_BRAND_CLEANUP="${RUN_SAFE_BRAND_CLEANUP:-false}"
HIDE_LEGACY_GROUPS="${HIDE_LEGACY_GROUPS:-}"
RUN_REPORT_LEGACY_LINKS="${RUN_REPORT_LEGACY_LINKS:-true}"
RUN_CLEANUP_LEGACY_LINKS="${RUN_CLEANUP_LEGACY_LINKS:-false}"
DRY_RUN="${DRY_RUN:-true}"
RUN_POST_DEPLOY_OPS="${RUN_POST_DEPLOY_OPS:-false}"

log() {
  local stage="$1"
  shift
  echo "[ops][${stage}] $*"
}

summary() {
  echo "$*" >> "${OPS_SUMMARY_FILE}"
}

: > "${OPS_SUMMARY_FILE}"
log init "start"
log init "RUN_POST_DEPLOY_OPS=${RUN_POST_DEPLOY_OPS}"
log init "OPS_MODE=${OPS_MODE}"
log init "RUN_NORMALIZE_LEGACY=${RUN_NORMALIZE_LEGACY}"
log init "RUN_BACKFILL_BRAND_SERIES=${RUN_BACKFILL_BRAND_SERIES}"
log init "RUN_SAFE_BRAND_CLEANUP=${RUN_SAFE_BRAND_CLEANUP}"
log init "HIDE_LEGACY_GROUPS=${HIDE_LEGACY_GROUPS:-<empty>}"
log init "RUN_REPORT_LEGACY_LINKS=${RUN_REPORT_LEGACY_LINKS}"
log init "RUN_CLEANUP_LEGACY_LINKS=${RUN_CLEANUP_LEGACY_LINKS}"
log init "DRY_RUN=${DRY_RUN}"

if [[ "${RUN_POST_DEPLOY_OPS}" != "true" ]]; then
  log init "RUN_POST_DEPLOY_OPS is not true, skipping."
  summary "mode=skipped"
  summary "reason=RUN_POST_DEPLOY_OPS is not true"
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  log preflight "docker is not installed"
  exit 1
fi
if ! command -v docker compose >/dev/null 2>&1; then
  log preflight "docker compose is not available"
  exit 1
fi
if [[ ! -d "${PROJECT_DIR}" ]]; then
  log preflight "project dir not found: ${PROJECT_DIR}"
  exit 1
fi

cd "${PROJECT_DIR}"
if [[ ! -f "docker-compose.prod.yml" ]]; then
  log preflight "docker-compose.prod.yml not found in ${PROJECT_DIR}"
  exit 1
fi

run_in_app() {
  ${COMPOSE} exec -T app sh -lc "$1"
}

script_exists() {
  run_in_app "test -f $1"
}

normalize_enabled="false"
backfill_brand_series_enabled="false"
report_enabled="true"
cleanup_enabled="false"
case "${OPS_MODE}" in
  report_only)
    normalize_enabled="false"
    report_enabled="true"
    cleanup_enabled="false"
    ;;
  normalize_report)
    normalize_enabled="true"
    report_enabled="true"
    cleanup_enabled="false"
    ;;
  full)
    normalize_enabled="true"
    report_enabled="true"
    cleanup_enabled="${RUN_CLEANUP_LEGACY_LINKS}"
    ;;
  *)
    log preflight "unsupported OPS_MODE=${OPS_MODE}"
    exit 1
    ;;
esac

if [[ "${RUN_NORMALIZE_LEGACY}" == "true" ]]; then
  normalize_enabled="true"
fi
if [[ "${RUN_BACKFILL_BRAND_SERIES}" == "true" ]]; then
  backfill_brand_series_enabled="true"
fi
if [[ "${RUN_REPORT_LEGACY_LINKS}" == "false" ]]; then
  report_enabled="false"
fi

log preflight "Ensuring app is running..."
${COMPOSE} up -d app >/dev/null

ops_actions=()
ops_skipped=()

if [[ "${normalize_enabled}" == "true" ]]; then
  if script_exists "scripts/normalize_legacy.py"; then
    log normalize "Running normalize_legacy.py"
    run_in_app "python3 scripts/normalize_legacy.py"
    ops_actions+=("normalize_legacy")
  else
    log normalize "Skip: scripts/normalize_legacy.py not found in image"
    ops_skipped+=("normalize_legacy:missing_script")
  fi
else
  ops_skipped+=("normalize_legacy:disabled")
fi

if [[ "${backfill_brand_series_enabled}" == "true" ]]; then
  if script_exists "scripts/backfill_brand_series.py"; then
    log backfill "Running backfill_brand_series.py"
    backfill_cmd="python3 scripts/backfill_brand_series.py"
    if [[ "${RUN_SAFE_BRAND_CLEANUP}" == "true" ]]; then
      backfill_cmd="${backfill_cmd} --safe-brand-cleanup"
    fi
    run_in_app "${backfill_cmd}"
    ops_actions+=("backfill_brand_series")
  else
    log backfill "Skip: scripts/backfill_brand_series.py not found in image"
    ops_skipped+=("backfill_brand_series:missing_script")
  fi
else
  ops_skipped+=("backfill_brand_series:disabled")
fi

if [[ -n "${HIDE_LEGACY_GROUPS}" ]]; then
  if script_exists "scripts/hide_legacy_tag_groups.py"; then
    log hide "Hiding legacy groups: ${HIDE_LEGACY_GROUPS}"
    run_in_app "python3 scripts/hide_legacy_tag_groups.py --groups ${HIDE_LEGACY_GROUPS}"
    ops_actions+=("hide_legacy_groups")
  else
    log hide "Skip: scripts/hide_legacy_tag_groups.py not found in image"
    ops_skipped+=("hide_legacy_groups:missing_script")
  fi
else
  ops_skipped+=("hide_legacy_groups:disabled")
fi

if [[ "${report_enabled}" == "true" ]]; then
  if script_exists "scripts/report_legacy_tag_links.py"; then
    log report "Report legacy links"
    run_in_app "python3 scripts/report_legacy_tag_links.py"
    ops_actions+=("report_legacy_links")
  else
    log report "Skip: scripts/report_legacy_tag_links.py not found in image"
    ops_skipped+=("report_legacy_links:missing_script")
  fi
else
  ops_skipped+=("report_legacy_links:disabled")
fi

if [[ "${cleanup_enabled}" == "true" ]]; then
  if script_exists "scripts/cleanup_legacy_tag_links.py"; then
    if [[ "${DRY_RUN}" == "true" ]]; then
      log cleanup "Cleanup dry-run"
      run_in_app "python3 scripts/cleanup_legacy_tag_links.py"
      ops_actions+=("cleanup_legacy_links:dry_run")
    else
      log cleanup "Cleanup execute=true"
      run_in_app "python3 scripts/cleanup_legacy_tag_links.py --execute"
      ops_actions+=("cleanup_legacy_links:execute")
    fi
  else
    log cleanup "Skip: scripts/cleanup_legacy_tag_links.py not found in image"
    ops_skipped+=("cleanup_legacy_links:missing_script")
  fi
else
  ops_skipped+=("cleanup_legacy_links:disabled")
fi

summary "mode=${OPS_MODE}"
summary "actions_run=${ops_actions[*]:-none}"
summary "actions_skipped=${ops_skipped[*]:-none}"
summary "dry_run=${DRY_RUN}"
log summary "mode=${OPS_MODE}"
log summary "actions_run=${ops_actions[*]:-none}"
log summary "actions_skipped=${ops_skipped[*]:-none}"
log done "completed"
