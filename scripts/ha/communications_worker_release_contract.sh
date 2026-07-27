#!/usr/bin/env bash

# Shell library. The caller owns COMPOSE, BACKEND_IMAGE and
# COMMUNICATIONS_WORKER_SERVICE.

COMMUNICATIONS_WORKER_FENCE_MARKER="${COMMUNICATIONS_WORKER_FENCE_MARKER:-${PROJECT_DIR}/.ha-communications-worker-release-fenced}"
COMMUNICATIONS_WORKER_CONTRACT_PROFILE=""
COMMUNICATIONS_WORKER_PROFILE_ENABLED=""
COMMUNICATIONS_WORKER_PROFILE_ALLOW_ALL=""

communications_worker_set_profile_gates() {
  case "$1" in
    dormant)
      COMMUNICATIONS_WORKER_PROFILE_ENABLED=false
      COMMUNICATIONS_WORKER_PROFILE_ALLOW_ALL=false
      ;;
    canary)
      COMMUNICATIONS_WORKER_PROFILE_ENABLED=true
      COMMUNICATIONS_WORKER_PROFILE_ALLOW_ALL=false
      ;;
    active)
      COMMUNICATIONS_WORKER_PROFILE_ENABLED=true
      COMMUNICATIONS_WORKER_PROFILE_ALLOW_ALL=true
      ;;
    *)
      echo "communications worker gate profile is not reviewed" >&2
      return 1
      ;;
  esac
}

communications_worker_require_safe_fence_marker() {
  [[ ! -e "${COMMUNICATIONS_WORKER_FENCE_MARKER}" \
    && ! -L "${COMMUNICATIONS_WORKER_FENCE_MARKER}" ]] && return 0
  python3 - "${COMMUNICATIONS_WORKER_FENCE_MARKER}" <<'PY'
import os
import stat
import sys

metadata = os.lstat(sys.argv[1])
if (
    not stat.S_ISREG(metadata.st_mode)
    or stat.S_ISLNK(metadata.st_mode)
    or metadata.st_uid != os.geteuid()
    or metadata.st_nlink != 1
    or metadata.st_mode & 0o077
):
    raise SystemExit("communications worker release fence metadata is unsafe")
PY
}

communications_worker_set_release_fence() {
  local temporary=""
  communications_worker_require_safe_fence_marker
  temporary="$(mktemp "${COMMUNICATIONS_WORKER_FENCE_MARKER}.tmp.XXXXXX")"
  if ! printf 'fenced\n' >"${temporary}" || ! chmod 0600 "${temporary}" \
    || ! mv -f -- "${temporary}" "${COMMUNICATIONS_WORKER_FENCE_MARKER}"; then
    rm -f -- "${temporary}"
    return 1
  fi
}

communications_worker_clear_release_fence() {
  local lock_fd="${DEPLOY_LOCK_FD:-${API_DEPLOY_LOCK_FD:-}}"
  [[ "${lock_fd}" == "9" ]] || {
    echo "communications worker release fence requires deploy lock fd 9" >&2
    return 1
  }
  communications_worker_require_safe_fence_marker
  rm -f -- "${COMMUNICATIONS_WORKER_FENCE_MARKER}"
}

communications_worker_require_release_unfenced() {
  if [[ -e "${COMMUNICATIONS_WORKER_FENCE_MARKER}" \
    || -L "${COMMUNICATIONS_WORKER_FENCE_MARKER}" ]]; then
    echo "communications worker release fence remains latched" >&2
    return 1
  fi
}

communications_worker_has_service() {
  local services=""
  services="$("${COMPOSE[@]}" config --services)" || {
    echo "could not render compose services for communications worker" >&2
    return 2
  }
  grep -Fxq "${COMMUNICATIONS_WORKER_SERVICE}" <<<"${services}" && return 0
  return 3
}

communications_worker_require_contract() {
  local expected_profile="${1:-}"
  local actual_profile=""
  local service_status=0
  if [[ -n "${expected_profile}" ]]; then
    communications_worker_set_profile_gates "${expected_profile}"
  fi
  communications_worker_has_service || service_status=$?
  [[ "${service_status}" -eq 0 ]] || {
    if [[ "${service_status}" -eq 3 ]]; then
      echo "compose is missing ${COMMUNICATIONS_WORKER_SERVICE}" >&2
    fi
    return "${service_status}"
  }
  actual_profile="$("${COMPOSE[@]}" config --format json \
    | python3 -c '
import json
import sys

service_name, expected_image = sys.argv[1:]
payload = json.load(sys.stdin)
service = (payload.get("services") or {}).get(service_name)
if not isinstance(service, dict):
    raise SystemExit("communications worker is absent from rendered compose")
if service.get("image") != expected_image:
    raise SystemExit("communications worker effective image differs from BACKEND_IMAGE")
environment = service.get("environment") or {}
if not isinstance(environment, dict):
    raise SystemExit("communications worker environment is not a mapping")
gates = (
    environment.get("COMMUNICATIONS_WORKER_ENABLED"),
    environment.get("COMMUNICATIONS_WORKER_ALLOW_ALL_MODE"),
)
profiles = {
    ("false", "false"): "dormant",
    ("true", "false"): "canary",
    ("true", "true"): "active",
}
profile = profiles.get(gates)
if profile is None:
    raise SystemExit("communications worker gate profile is not reviewed")
print(profile)
' "${COMMUNICATIONS_WORKER_SERVICE}" "${BACKEND_IMAGE}")" || return 1
  communications_worker_set_profile_gates "${actual_profile}"
  if [[ -n "${expected_profile}" && "${actual_profile}" != "${expected_profile}" ]]; then
    echo "communications worker gate profile differs from the expected release" >&2
    return 1
  fi
  COMMUNICATIONS_WORKER_CONTRACT_PROFILE="${actual_profile}"
}

communications_worker_require_runtime() {
  local expected_role="${1:-${EXPECTED_ROLE:-}}"
  local expected_profile="${2:-}"
  local expected_enabled=""
  local expected_allow_all=""
  local container_ids=""
  local runtime=""
  communications_worker_require_release_unfenced
  [[ "${expected_role}" == "primary" || "${expected_role}" == "standby" ]] || {
    echo "communications worker runtime role expectation is invalid" >&2
    return 1
  }
  communications_worker_require_contract "${expected_profile}"
  expected_profile="${COMMUNICATIONS_WORKER_CONTRACT_PROFILE}"
  communications_worker_set_profile_gates "${expected_profile}"
  expected_enabled="${COMMUNICATIONS_WORKER_PROFILE_ENABLED}"
  expected_allow_all="${COMMUNICATIONS_WORKER_PROFILE_ALLOW_ALL}"
  container_ids="$("${COMPOSE[@]}" ps -q "${COMMUNICATIONS_WORKER_SERVICE}")"
  [[ -n "${container_ids}" && "${container_ids}" != *$'\n'* ]] || {
    echo "expected exactly one running communications worker container" >&2
    return 1
  }
  runtime="$(docker inspect --format '{{.Config.Image}}|{{.State.Running}}' \
    "${container_ids}")"
  [[ "${runtime}" == "${BACKEND_IMAGE}|true" ]] || {
    echo "communications worker runtime does not match BACKEND_IMAGE" >&2
    return 1
  }
  if ! "${COMPOSE[@]}" exec -T "${COMMUNICATIONS_WORKER_SERVICE}" \
    python3 -c '
import os
import sys

expected_role, expected_enabled, expected_allow_all = sys.argv[1:]
valid = (
    os.environ.get("APP_ROLE") == expected_role
    and os.environ.get("COMMUNICATIONS_WORKER_ENABLED") == expected_enabled
    and os.environ.get("COMMUNICATIONS_WORKER_ALLOW_ALL_MODE")
    == expected_allow_all
)
raise SystemExit(0 if valid else 1)
' "${expected_role}" "${expected_enabled}" "${expected_allow_all}" >/dev/null; then
    echo "communications worker runtime role or gate profile drifted" >&2
    return 1
  fi
}

communications_worker_start_controlled() {
  local expected_role="$1"
  local expected_profile="${2:-}"
  if ! communications_worker_require_contract "${expected_profile}"; then
    communications_worker_set_release_fence || true
    return 1
  fi
  expected_profile="${COMMUNICATIONS_WORKER_CONTRACT_PROFILE}"
  communications_worker_clear_release_fence
  if ! "${COMPOSE[@]}" up -d --no-deps --force-recreate \
    "${COMMUNICATIONS_WORKER_SERVICE}" \
    || ! communications_worker_require_runtime "${expected_role}" "${expected_profile}"; then
    communications_worker_set_release_fence || true
    "${COMPOSE[@]}" stop "${COMMUNICATIONS_WORKER_SERVICE}" >/dev/null 2>&1 || true
    return 1
  fi
}
