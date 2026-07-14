#!/usr/bin/env bash

DEPLOY_CAPACITY_MEMINFO_FILE="${API_DEPLOY_MEMINFO_FILE:-/proc/meminfo}"
DEPLOY_CAPACITY_PROFILE="${API_DEPLOY_CAPACITY_PROFILE:-primary}"
DEPLOY_MIN_FREE_SWAP_KIB="${API_DEPLOY_MIN_FREE_SWAP_KIB:-262144}"

deploy_capacity_error() {
  printf '[deploy-capacity][error] %s\n' "$1" >&2
}

case "${DEPLOY_CAPACITY_PROFILE}" in
  primary) default_min_available_memory_kib=1572864 ;;
  reserve) default_min_available_memory_kib=1048576 ;;
  *) deploy_capacity_error "API_DEPLOY_CAPACITY_PROFILE must be primary or reserve"; return 1 2>/dev/null || exit 1 ;;
esac
# Keep 512 MiB beyond the node's maximum candidate-app cgroup.
DEPLOY_MIN_AVAILABLE_MEMORY_KIB="${API_DEPLOY_MIN_AVAILABLE_MEMORY_KIB:-${default_min_available_memory_kib}}"

deploy_capacity_meminfo_value() {
  local key="$1"
  awk -v key="${key}:" '
    $1 == key { value = $2; matches += 1 }
    END { if (matches != 1 || value !~ /^[0-9]+$/) exit 1; print value }
  ' "${DEPLOY_CAPACITY_MEMINFO_FILE}"
}

require_deploy_capacity() {
  local available_kib=""
  local swap_total_kib=""
  local swap_free_kib=""

  [[ "${DEPLOY_MIN_AVAILABLE_MEMORY_KIB}" =~ ^[1-9][0-9]*$ ]] || {
    deploy_capacity_error "API_DEPLOY_MIN_AVAILABLE_MEMORY_KIB must be a positive integer"
    return 1
  }
  [[ "${DEPLOY_MIN_FREE_SWAP_KIB}" =~ ^[1-9][0-9]*$ ]] || {
    deploy_capacity_error "API_DEPLOY_MIN_FREE_SWAP_KIB must be a positive integer"
    return 1
  }
  [[ -r "${DEPLOY_CAPACITY_MEMINFO_FILE}" ]] || {
    deploy_capacity_error "cannot read host memory capacity: ${DEPLOY_CAPACITY_MEMINFO_FILE}"
    return 1
  }

  available_kib="$(deploy_capacity_meminfo_value MemAvailable)" || {
    deploy_capacity_error "MemAvailable is missing or invalid in ${DEPLOY_CAPACITY_MEMINFO_FILE}"
    return 1
  }
  swap_total_kib="$(deploy_capacity_meminfo_value SwapTotal)" || {
    deploy_capacity_error "SwapTotal is missing or invalid in ${DEPLOY_CAPACITY_MEMINFO_FILE}"
    return 1
  }
  swap_free_kib="$(deploy_capacity_meminfo_value SwapFree)" || {
    deploy_capacity_error "SwapFree is missing or invalid in ${DEPLOY_CAPACITY_MEMINFO_FILE}"
    return 1
  }
  (( swap_free_kib <= swap_total_kib )) || {
    deploy_capacity_error "SwapFree exceeds SwapTotal in ${DEPLOY_CAPACITY_MEMINFO_FILE}"
    return 1
  }
  (( available_kib >= DEPLOY_MIN_AVAILABLE_MEMORY_KIB )) || {
    deploy_capacity_error "insufficient memory headroom: available=${available_kib}KiB required=${DEPLOY_MIN_AVAILABLE_MEMORY_KIB}KiB"
    return 1
  }
  if (( swap_total_kib > 0 && swap_free_kib < DEPLOY_MIN_FREE_SWAP_KIB )); then
    deploy_capacity_error "insufficient free swap reserve: free=${swap_free_kib}KiB required=${DEPLOY_MIN_FREE_SWAP_KIB}KiB"
    return 1
  fi
}
