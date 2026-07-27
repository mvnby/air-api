#!/usr/bin/env bash
# shellcheck disable=SC2034  # lifecycle state is consumed by the sourcing caller

# Shell library for the communications-worker portion of a Patroni candidate
# transaction. The caller supplies the canonical/candidate paths and release
# image globals.

COMMUNICATIONS_WORKER_SERVICE="${API_COMMUNICATIONS_WORKER_SERVICE:-communications-worker}"
PREVIOUS_WORKER_SUPPORTED=false
PREVIOUS_WORKER_RUNNING=false
PREVIOUS_WORKER_GATE_PROFILE=""
CANDIDATE_WORKER_SUPPORTED=false
CANDIDATE_WORKER_GATE_PROFILE=""
CANONICAL_WORKER_PROJECT=""
CANDIDATE_WORKER_PROJECT=""
PREVIOUS_WORKER_FENCE_MARKER_PRESENT=false

patroni_communications_capture_release_fence() {
  if [[ -e "${COMMUNICATIONS_WORKER_FENCE_MARKER}" \
    || -L "${COMMUNICATIONS_WORKER_FENCE_MARKER}" ]]; then
    PREVIOUS_WORKER_FENCE_MARKER_PRESENT=true
  fi
  communications_worker_require_safe_fence_marker
}

patroni_communications_restore_release_fence() {
  if [[ "${PREVIOUS_WORKER_FENCE_MARKER_PRESENT}" == "true" ]]; then
    communications_worker_set_release_fence
  else
    communications_worker_clear_release_fence
  fi
}

patroni_communications_require_previous_fence_restored() {
  [[ "${PREVIOUS_WORKER_FENCE_MARKER_PRESENT}" == "true" ]] || return 0
  local running=""
  if [[ "${PREVIOUS_WORKER_SUPPORTED}" == "true" ]]; then
    running="$(docker compose -f "${CANONICAL_FILE}" --profile bluegreen \
      ps --status running -q "${COMMUNICATIONS_WORKER_SERVICE}")" || return 1
  else
    [[ -n "${CANONICAL_WORKER_PROJECT}" ]] || {
      echo "canonical Compose project identity is unavailable" >&2
      return 1
    }
    running="$(docker ps -a -q \
      --filter "label=com.docker.compose.project=${CANONICAL_WORKER_PROJECT}" \
      --filter "label=com.docker.compose.service=${COMMUNICATIONS_WORKER_SERVICE}")" \
      || return 1
  fi
  [[ -z "${running}" ]] || {
    echo "communications worker restarted under the restored release fence" >&2
    return 1
  }
}

patroni_communications_compose_project() {
  local compose_file="$1"

  docker compose -f "${compose_file}" --profile bluegreen \
    config --format json \
    | python3 -c '
import json
import re
import sys

name = (json.load(sys.stdin) or {}).get("name")
if not isinstance(name, str) or re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,126}", name) is None:
    raise SystemExit(1)
print(name)
'
}

patroni_communications_compose_has_worker() {
  local compose_file="$1"
  local service_status=0
  # shellcheck disable=SC2034  # consumed by the release-contract helper
  local -a COMPOSE=(docker compose -f "${compose_file}" --profile bluegreen)

  communications_worker_has_service || service_status=$?
  [[ "${service_status}" -ne 2 ]] || {
    echo "could not establish communications worker service support" >&2
    exit 86
  }
  [[ "${service_status}" -eq 0 ]]
}

patroni_communications_require_runtime() {
  local compose_file="$1"
  local expected_image="$2"
  local expected_profile="$3"

  API_RECONCILE_OPERATION=verify \
    API_DEPLOY_SERVICES="${COMMUNICATIONS_WORKER_SERVICE}" \
    API_COMPOSE_FILE="$(basename "${compose_file}")" \
    API_RECONCILE_BACKEND_IMAGE="${expected_image}" \
    API_EXPECTED_PATRONI_ROLE="${EXPECTED_ROLE}" \
    API_COMMUNICATIONS_WORKER_EXPECTED_PROFILE="${expected_profile}" \
    bash "${RECONCILE_SCRIPT}"
}

patroni_communications_capture_previous() {
  local container_ids=""
  local runtime=""

  CANONICAL_WORKER_PROJECT="$(
    patroni_communications_compose_project "${CANONICAL_FILE}"
  )" || {
    echo "canonical Compose project identity is invalid" >&2
    return 1
  }
  patroni_communications_compose_has_worker "${CANONICAL_FILE}" || return 0
  PREVIOUS_WORKER_SUPPORTED=true
  local BACKEND_IMAGE="${PREVIOUS_BACKEND_IMAGE}"
  # shellcheck disable=SC2034  # consumed by the release-contract helper
  local -a COMPOSE=(
    docker compose -f "${CANONICAL_FILE}" --profile bluegreen
  )
  export BACKEND_IMAGE
  communications_worker_require_contract
  PREVIOUS_WORKER_GATE_PROFILE="${COMMUNICATIONS_WORKER_CONTRACT_PROFILE}"

  if [[ "${PREVIOUS_WORKER_FENCE_MARKER_PRESENT}" == "true" ]]; then
    container_ids="$(docker compose -f "${CANONICAL_FILE}" --profile bluegreen \
      ps --status running -q "${COMMUNICATIONS_WORKER_SERVICE}")"
    [[ -z "${container_ids}" ]] || {
      echo "latched communications worker release fence has a running worker" >&2
      return 1
    }
    return 0
  fi

  container_ids="$(docker compose -f "${CANONICAL_FILE}" --profile bluegreen \
    ps -q "${COMMUNICATIONS_WORKER_SERVICE}")"
  [[ -n "${container_ids}" && "${container_ids}" != *$'\n'* ]] || {
    echo "previous communications worker runtime is ambiguous" >&2
    return 1
  }
  runtime="$(docker inspect --format '{{.Config.Image}}|{{.State.Running}}' \
    "${container_ids}")"
  [[ "${runtime}" == "${PREVIOUS_BACKEND_IMAGE}|true" ]] || {
    echo "previous communications worker is not aligned with the active API image" >&2
    return 1
  }
  PREVIOUS_WORKER_RUNNING=true
}

patroni_communications_detect_candidate_support() {
  local candidate_image="${BACKEND_IMAGE}"
  CANDIDATE_WORKER_PROJECT="$(
    patroni_communications_compose_project "${CANDIDATE_FILE}"
  )" || {
    echo "candidate communications worker Compose project is invalid" >&2
    return 1
  }
  if patroni_communications_compose_has_worker "${CANDIDATE_FILE}"; then
    CANDIDATE_WORKER_SUPPORTED=true
    local BACKEND_IMAGE="${candidate_image}"
    # shellcheck disable=SC2034  # consumed by the release-contract helper
    local -a COMPOSE=(
      docker compose -f "${CANDIDATE_FILE}" --profile bluegreen
    )
    export BACKEND_IMAGE
    communications_worker_require_contract
    CANDIDATE_WORKER_GATE_PROFILE="${COMMUNICATIONS_WORKER_CONTRACT_PROFILE}"
  fi
}

patroni_communications_force_fence_candidate_runtime() {
  [[ "${CANDIDATE_WORKER_SUPPORTED}" == "true" ]] || return 0
  communications_worker_set_release_fence
  [[ -n "${CANDIDATE_WORKER_PROJECT}" ]] || {
    echo "candidate communications worker project identity is unavailable" >&2
    return 1
  }
  local container_ids=""
  local remaining=""
  local container_id=""
  local -a exact_ids=()

  container_ids="$(docker ps -a -q \
    --filter "label=com.docker.compose.project=${CANDIDATE_WORKER_PROJECT}" \
    --filter "label=com.docker.compose.service=${COMMUNICATIONS_WORKER_SERVICE}")" \
    || return 1
  while IFS= read -r container_id; do
    [[ -z "${container_id}" ]] && continue
    [[ "${container_id}" =~ ^[0-9a-f]{12,64}$ ]] || {
      echo "candidate communications worker container identity is invalid" >&2
      return 1
    }
    exact_ids+=("${container_id}")
  done <<<"${container_ids}"
  if [[ "${#exact_ids[@]}" -gt 0 ]]; then
    docker rm -f -- "${exact_ids[@]}" >/dev/null || return 1
  fi
  remaining="$(docker ps -a -q \
    --filter "label=com.docker.compose.project=${CANDIDATE_WORKER_PROJECT}" \
    --filter "label=com.docker.compose.service=${COMMUNICATIONS_WORKER_SERVICE}")" \
    || return 1
  [[ -z "${remaining}" ]] || {
    echo "candidate communications worker remained after forced fence" >&2
    return 1
  }
}

patroni_communications_fence_candidate() {
  [[ "${CANDIDATE_WORKER_SUPPORTED}" == "true" ]] || return 0
  communications_worker_set_release_fence
  if ! docker compose -f "${CANDIDATE_FILE}" --profile bluegreen \
    stop "${COMMUNICATIONS_WORKER_SERVICE}" >/dev/null; then
    patroni_communications_force_fence_candidate_runtime || return 1
    return 0
  fi
  if [[ "${PREVIOUS_WORKER_SUPPORTED}" != "true" ]]; then
    if ! docker compose -f "${CANDIDATE_FILE}" --profile bluegreen \
      rm -s -f "${COMMUNICATIONS_WORKER_SERVICE}" >/dev/null; then
      patroni_communications_force_fence_candidate_runtime || return 1
      return 0
    fi
    patroni_communications_force_fence_candidate_runtime || return 1
  fi
  return 0
}

patroni_communications_fence_canonical() {
  [[ "${CANDIDATE_WORKER_SUPPORTED}" == "true" ]] || return 0
  communications_worker_set_release_fence
  docker compose -f "${CANONICAL_FILE}" --profile bluegreen \
    stop "${COMMUNICATIONS_WORKER_SERVICE}" >/dev/null
}
