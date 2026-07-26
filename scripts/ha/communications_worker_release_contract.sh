#!/usr/bin/env bash

# Shell library. The caller owns COMPOSE, BACKEND_IMAGE and
# COMMUNICATIONS_WORKER_SERVICE.

COMMUNICATIONS_WORKER_FENCE_MARKER="${COMMUNICATIONS_WORKER_FENCE_MARKER:-${PROJECT_DIR}/.ha-communications-worker-release-fenced}"

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
  local service_status=0
  communications_worker_has_service || service_status=$?
  [[ "${service_status}" -eq 0 ]] || {
    if [[ "${service_status}" -eq 3 ]]; then
      echo "compose is missing ${COMMUNICATIONS_WORKER_SERVICE}" >&2
    fi
    return "${service_status}"
  }
  "${COMPOSE[@]}" config --format json \
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
for key in (
    "COMMUNICATIONS_WORKER_ENABLED",
    "COMMUNICATIONS_WORKER_ALLOW_ALL_MODE",
):
    if str(environment.get(key, "")).lower() != "false":
        raise SystemExit(f"{key} must remain false during Phase 2A")
' "${COMMUNICATIONS_WORKER_SERVICE}" "${BACKEND_IMAGE}"
}

communications_worker_require_runtime() {
  local expected_role="${1:-${EXPECTED_ROLE:-}}"
  local container_ids=""
  local runtime=""
  communications_worker_require_release_unfenced
  [[ "${expected_role}" == "primary" || "${expected_role}" == "standby" ]] || {
    echo "communications worker runtime role expectation is invalid" >&2
    return 1
  }
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

expected_role = sys.argv[1]
valid = (
    os.environ.get("APP_ROLE") == expected_role
    and os.environ.get("COMMUNICATIONS_WORKER_ENABLED", "").lower() == "false"
    and os.environ.get("COMMUNICATIONS_WORKER_ALLOW_ALL_MODE", "").lower() == "false"
)
raise SystemExit(0 if valid else 1)
' "${expected_role}" >/dev/null; then
    echo "communications worker runtime role or Phase 2A gates drifted" >&2
    return 1
  fi
}

communications_worker_start_controlled() {
  local expected_role="$1"
  communications_worker_clear_release_fence
  if ! "${COMPOSE[@]}" up -d --no-deps --force-recreate \
    "${COMMUNICATIONS_WORKER_SERVICE}" \
    || ! communications_worker_require_runtime "${expected_role}"; then
    communications_worker_set_release_fence || true
    "${COMPOSE[@]}" stop "${COMMUNICATIONS_WORKER_SERVICE}" >/dev/null 2>&1 || true
    return 1
  fi
}
