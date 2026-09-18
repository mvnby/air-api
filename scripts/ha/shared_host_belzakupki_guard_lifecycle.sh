#!/usr/bin/env bash
# Sourced by backend candidate transactions after their primary deploy lock has
# been verified. The caller supplies DEPLOY_LOCK_HELPER and the guarded script.

shared_belzakupki_guard_initialize() {
  : "${SHARED_HOST_BELZAKUPKI_GUARD:=${API_SHARED_HOST_BELZAKUPKI_GUARD:-auto}}"
  : "${SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE:=${API_SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE:-}}"
  : "${SHARED_HOST_BELZAKUPKI_LOCK_FILE:=${API_SHARED_HOST_BELZAKUPKI_LOCK_FILE:-/var/lock/mvn-shared-host-belzakupki.lock}}"
  : "${SHARED_HOST_BELZAKUPKI_LOCK_FD:=${API_SHARED_HOST_BELZAKUPKI_LOCK_FD:-}}"
  : "${SHARED_HOST_BELZAKUPKI_GUARD_SCRIPT:=${API_SHARED_HOST_BELZAKUPKI_GUARD_SCRIPT:?shared Belzakupki guard script is required}}"
}

shared_belzakupki_guard_setup() {
  local guard_status
  case "${SHARED_HOST_BELZAKUPKI_GUARD}" in
    false|auto|true) ;;
    *) echo "API_SHARED_HOST_BELZAKUPKI_GUARD must be auto, true, or false" >&2; return 1 ;;
  esac
  if [[ -z "${SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE}" ]]; then
    [[ -f "${SHARED_HOST_BELZAKUPKI_GUARD_SCRIPT}" \
      && ! -L "${SHARED_HOST_BELZAKUPKI_GUARD_SCRIPT}" ]] || {
      echo "shared Belzakupki guard script is missing or unsafe" >&2; return 1;
    }
    guard_status="$(API_SHARED_HOST_BELZAKUPKI_GUARD="${SHARED_HOST_BELZAKUPKI_GUARD}" \
      bash "${SHARED_HOST_BELZAKUPKI_GUARD_SCRIPT}" enabled)" || return 1
    case "${guard_status}" in
      enabled) SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE=true ;;
      disabled) SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE=false ;;
      *) echo "shared Belzakupki guard returned an invalid status" >&2; return 1 ;;
    esac
    export API_SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE="${SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE}"
  fi
  if [[ "${SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE}" == "true" ]]; then
    [[ "${SHARED_HOST_BELZAKUPKI_LOCK_FILE}" == "/var/lock/mvn-shared-host-belzakupki.lock" ]] || {
      echo "shared Belzakupki lock path is fixed" >&2; return 1;
    }
    if [[ -z "${SHARED_HOST_BELZAKUPKI_LOCK_FD}" ]]; then
      exec python3 "${DEPLOY_LOCK_HELPER}" exec-with-fd \
        "${SHARED_HOST_BELZAKUPKI_LOCK_FILE}" 8 \
        API_SHARED_HOST_BELZAKUPKI_LOCK_FD bash "$0" "$@"
    fi
    [[ "${SHARED_HOST_BELZAKUPKI_LOCK_FD}" == "8" ]] || {
      echo "shared Belzakupki guard requires inherited lock fd 8" >&2; return 1;
    }
    python3 "${DEPLOY_LOCK_HELPER}" verify \
      "${SHARED_HOST_BELZAKUPKI_LOCK_FILE}" "${SHARED_HOST_BELZAKUPKI_LOCK_FD}"
  elif [[ "${SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE}" != "false" ]]; then
    echo "API_SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE must be true or false" >&2
    return 1
  fi
}

shared_belzakupki_guard_prepare() {
  [[ "${SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE}" == "true" ]] || return 0
  API_SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE="${SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE}" \
    bash "${SHARED_HOST_BELZAKUPKI_GUARD_SCRIPT}" prepare
}

shared_belzakupki_guard_restore() {
  [[ "${SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE}" == "true" ]] || return 0
  API_SHARED_HOST_BELZAKUPKI_GUARD="${SHARED_HOST_BELZAKUPKI_GUARD}" \
    API_SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE="${SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE}" \
    bash "${SHARED_HOST_BELZAKUPKI_GUARD_SCRIPT}" restore
}

shared_belzakupki_guard_prepare_with_signal_recovery() {
  shared_belzakupki_guard_prepare
  if [[ "${SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE}" == "true" ]]; then
    trap 'exit 143' INT TERM
  fi
}

shared_belzakupki_guard_clear_signal_recovery() {
  trap - INT TERM
}

shared_belzakupki_guard_cleanup_candidate_transaction() {
  local status=$?
  trap - EXIT
  set +e
  [[ "${CANDIDATE_OWNED}" == "true" ]] && transaction cleanup
  shared_belzakupki_guard_restore || status=90
  exit "${status}"
}
