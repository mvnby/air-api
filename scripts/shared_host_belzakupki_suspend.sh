#!/usr/bin/env bash
# Suspend only the separately deployed Belzakupki queue processes while an
# air-api release needs the shared Belarus host's memory.  This deliberately
# never invokes compose down/stop, so Caddy, API, and PostgreSQL stay outside
# this guard's authority.
set -Eeuo pipefail

ACTION="${1:-}"
GUARD_ENABLED="${API_SHARED_HOST_BELZAKUPKI_GUARD:-auto}"
GUARD_ACTIVE="${API_SHARED_HOST_BELZAKUPKI_GUARD_ACTIVE:-false}"
BELZAKUPKI_DIR="${API_SHARED_HOST_BELZAKUPKI_DIR:-/opt/belzakupki}"
STATE_FILE="${BELZAKUPKI_DIR}/.air-api-deploy-suspension"
MARKER_FILE="${BELZAKUPKI_DIR}/.kitlane-deploy-guard-enabled"
STOP_TIMEOUT_SECONDS="${API_SHARED_HOST_BELZAKUPKI_STOP_TIMEOUT_SECONDS:-120}"
EXPECTED_DIR="/opt/belzakupki"
EXPECTED_PROJECT="belzakupki"

die() {
  echo "shared Belzakupki guard: $*" >&2
  exit 1
}

marker_is_safe() {
  [[ -f "${MARKER_FILE}" && ! -L "${MARKER_FILE}" ]] || return 1
  python3 - "${BELZAKUPKI_DIR}" "${MARKER_FILE}" <<'PY'
import os, stat, sys
directory, marker = sys.argv[1:]
directory_metadata = os.lstat(directory)
metadata = os.lstat(marker)
if (not stat.S_ISDIR(directory_metadata.st_mode) or stat.S_ISLNK(directory_metadata.st_mode)
        or directory_metadata.st_uid != 0 or directory_metadata.st_mode & 0o022
        or not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0 or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600):
    raise SystemExit("unsafe shared Belzakupki enable marker")
PY
}

is_enabled() {
  [[ "${GUARD_ACTIVE}" == "true" ]] && return 0
  case "${GUARD_ENABLED}" in
    false) return 1 ;;
    auto|true) ;;
    *) die "API_SHARED_HOST_BELZAKUPKI_GUARD must be auto, true, or false" ;;
  esac
  [[ "${BELZAKUPKI_DIR}" == "${EXPECTED_DIR}" ]] || {
    die "Belzakupki directory must be ${EXPECTED_DIR}";
  }
  if [[ -e "${MARKER_FILE}" || -L "${MARKER_FILE}" ]]; then
    marker_is_safe || die "enable marker is unsafe: ${MARKER_FILE}"
  elif [[ "${GUARD_ENABLED}" == "true" ]]; then
    die "enable marker is required: ${MARKER_FILE}"
  else
    return 1
  fi
  [[ "${STOP_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] \
    && (( STOP_TIMEOUT_SECONDS <= 600 )) || {
      die "API_SHARED_HOST_BELZAKUPKI_STOP_TIMEOUT_SECONDS must be an integer from 1 to 600";
    }
}

enabled_status() {
  if is_enabled; then
    printf 'enabled\n'
  else
    printf 'disabled\n'
  fi
}

validate_state_file() {
  [[ -f "${STATE_FILE}" && ! -L "${STATE_FILE}" ]] || return 1
  python3 - "${BELZAKUPKI_DIR}" "${STATE_FILE}" <<'PY'
import os, stat, sys
directory, path = sys.argv[1:]
directory_metadata = os.lstat(directory)
metadata = os.lstat(path)
if (not stat.S_ISDIR(directory_metadata.st_mode) or stat.S_ISLNK(directory_metadata.st_mode)
        or directory_metadata.st_uid != os.geteuid() or directory_metadata.st_mode & 0o022
        or not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid() or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600):
    raise SystemExit("unsafe shared Belzakupki recovery record")
PY
}

SCHEDULER_STATE=stopped
SCHEDULER_ID=""
SCHEDULER_PHASE=running
WORKER_STATE=stopped
WORKER_ID=""
WORKER_PHASE=running

field_for() {
  local service="$1" field="$2"
  case "${service}:${field}" in
    scheduler:state) printf '%s\n' "${SCHEDULER_STATE}" ;;
    scheduler:id) printf '%s\n' "${SCHEDULER_ID}" ;;
    scheduler:phase) printf '%s\n' "${SCHEDULER_PHASE}" ;;
    worker:state) printf '%s\n' "${WORKER_STATE}" ;;
    worker:id) printf '%s\n' "${WORKER_ID}" ;;
    worker:phase) printf '%s\n' "${WORKER_PHASE}" ;;
    *) die "unknown Belzakupki service field" ;;
  esac
}

set_field() {
  local service="$1" field="$2" value="$3"
  case "${service}:${field}" in
    scheduler:state) SCHEDULER_STATE="${value}" ;;
    scheduler:id) SCHEDULER_ID="${value}" ;;
    scheduler:phase) SCHEDULER_PHASE="${value}" ;;
    worker:state) WORKER_STATE="${value}" ;;
    worker:id) WORKER_ID="${value}" ;;
    worker:phase) WORKER_PHASE="${value}" ;;
    *) die "unknown Belzakupki service field" ;;
  esac
}

load_state() {
  validate_state_file || die "recovery record is unsafe: ${STATE_FILE}"
  local version="" scheduler="" worker="" extra=""
  while IFS= read -r line || [[ -n "${line}" ]]; do
    case "${line}" in
      version=*) version="${line#version=}" ;;
      scheduler=*) scheduler="${line#scheduler=}" ;;
      worker=*) worker="${line#worker=}" ;;
      *) extra=1 ;;
    esac
  done < "${STATE_FILE}"
  [[ -z "${extra}" && "${version}" == "1" && -n "${scheduler}" && -n "${worker}" ]] \
    || die "recovery record has an invalid format"

  local service value state id phase trailing
  for service in scheduler worker; do
    value="${!service}"
    IFS='|' read -r state id phase trailing <<< "${value}"
    [[ -z "${trailing}" && "${state}" =~ ^(running|stopped)$ \
      && "${phase}" =~ ^(running|stopping|stopped)$ ]] \
      || die "recovery record has invalid ${service} state"
    if [[ "${state}" == "running" ]]; then
      [[ "${id}" =~ ^[0-9a-f]{64}$ ]] || die "recovery record has invalid ${service} id"
    else
      [[ -z "${id}" && "${phase}" == "running" ]] \
        || die "recovery record has invalid stopped ${service} state"
    fi
    set_field "${service}" state "${state}"
    set_field "${service}" id "${id}"
    set_field "${service}" phase "${phase}"
  done
}

write_state() {
  local temp
  umask 077
  temp="$(mktemp "${BELZAKUPKI_DIR}/.air-api-deploy-suspension.tmp.XXXXXX")"
  chmod 600 "${temp}"
  {
    printf 'version=1\n'
    printf 'scheduler=%s|%s|%s\n' "${SCHEDULER_STATE}" "${SCHEDULER_ID}" "${SCHEDULER_PHASE}"
    printf 'worker=%s|%s|%s\n' "${WORKER_STATE}" "${WORKER_ID}" "${WORKER_PHASE}"
  } > "${temp}"
  mv -f "${temp}" "${STATE_FILE}"
}

running_container_id() {
  local service="$1" id raw_ids line_count
  raw_ids="$(docker ps -q --no-trunc \
      --filter "label=com.docker.compose.project=${EXPECTED_PROJECT}" \
      --filter "label=com.docker.compose.service=${service}"
  )" || die "cannot list running Belzakupki ${service} containers"
  line_count="$(printf '%s\n' "${raw_ids}" | sed '/^$/d' | wc -l | tr -d ' ')"
  (( line_count <= 1 )) || die "more than one running Belzakupki ${service} container"
  if (( line_count == 1 )); then
    id="${raw_ids}"
    validate_container "${service}" "${id}"
    printf '%s\n' "${id}"
  fi
}

validate_container() {
  local service="$1" id="$2" metadata
  metadata="$(docker inspect --format '{{.Name}}|{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "${id}")" \
    || die "cannot inspect Belzakupki ${service} container ${id}"
  [[ "${metadata}" == "/belzakupki-${service}-1|${EXPECTED_PROJECT}|${service}|${EXPECTED_DIR}" ]] \
    || die "container ${id} is not the expected Belzakupki ${service} runtime"
}

container_status() {
  docker inspect --format '{{.State.Status}}' "$1" 2>/dev/null || true
}

wait_until_stopped() {
  local service="$1" id="$2" elapsed=0 status
  while (( elapsed <= STOP_TIMEOUT_SECONDS )); do
    status="$(container_status "${id}")"
    case "${status}" in
      exited|dead) return 0 ;;
      running|restarting|created|paused) ;;
      "") return 1 ;;
      *) return 1 ;;
    esac
    (( elapsed == STOP_TIMEOUT_SECONDS )) && break
    sleep 1
    ((elapsed += 1))
  done
  echo "shared Belzakupki guard: ${service} did not finish graceful SIGTERM within ${STOP_TIMEOUT_SECONDS}s; deployment is aborted without SIGKILL" >&2
  return 1
}

stop_service() {
  local service="$1" id="$(field_for "$1" id)"
  [[ "$(field_for "${service}" state)" == "running" ]] || return 0
  set_field "${service}" phase stopping
  write_state
  echo "Pausing Belzakupki ${service} with SIGTERM (no forced kill)"
  docker kill --signal=TERM "${id}" >/dev/null
  if ! wait_until_stopped "${service}" "${id}"; then
    return 1
  fi
  set_field "${service}" phase stopped
  write_state
}

restore_service() {
  local service="$1" id="$(field_for "$1" id)" status current_id
  if [[ "$(field_for "${service}" state)" == "stopped" ]]; then
    current_id="$(running_container_id "${service}")" || return 1
    [[ -z "${current_id}" ]] \
      || die "Belzakupki ${service} was originally stopped but is now running"
    return 0
  fi

  validate_container "${service}" "${id}"
  status="$(container_status "${id}")"
  if [[ "${status}" == "running" ]]; then
    [[ "$(field_for "${service}" phase)" != "stopping" ]] || {
      echo "shared Belzakupki guard: ${service} is still handling its graceful shutdown; recovery is not proven" >&2
      return 1
    }
    return 0
  fi
  [[ "${status}" == "exited" || "${status}" == "dead" ]] || {
    echo "shared Belzakupki guard: ${service} is in unexpected state ${status:-missing}" >&2
    return 1
  }
  echo "Restoring previously running Belzakupki ${service}"
  docker start "${id}" >/dev/null
  [[ "$(container_status "${id}")" == "running" ]] \
    || die "Belzakupki ${service} did not restart"
}

restore() {
  is_enabled || return 0
  [[ -e "${STATE_FILE}" ]] || return 0
  load_state
  local failed=false
  restore_service worker || failed=true
  restore_service scheduler || failed=true
  if [[ "${failed}" == "true" ]]; then
    echo "shared Belzakupki guard: recovery record retained at ${STATE_FILE}" >&2
    return 1
  fi
  rm -f "${STATE_FILE}"
  echo "Restored the original Belzakupki worker/scheduler state"
}

prepare() {
  is_enabled || {
    echo "shared Belzakupki guard disabled"
    return 0
  }
  [[ -d "${BELZAKUPKI_DIR}" && ! -L "${BELZAKUPKI_DIR}" ]] \
    || die "expected Belzakupki directory is unavailable: ${BELZAKUPKI_DIR}"
  if [[ -e "${STATE_FILE}" ]]; then
    echo "Recovering a stale Belzakupki suspension record before deployment"
    restore || die "stale Belzakupki recovery did not complete"
  fi

  SCHEDULER_STATE=stopped; SCHEDULER_ID=""; SCHEDULER_PHASE=running
  WORKER_STATE=stopped; WORKER_ID=""; WORKER_PHASE=running
  local service id
  for service in scheduler worker; do
    id="$(running_container_id "${service}")"
    if [[ -n "${id}" ]]; then
      set_field "${service}" state running
      set_field "${service}" id "${id}"
    fi
  done
  if [[ "${SCHEDULER_STATE}" == "stopped" && "${WORKER_STATE}" == "stopped" ]]; then
    echo "Belzakupki worker and scheduler were already stopped"
    return 0
  fi
  write_state
  trap 'restore || true; exit 143' INT TERM
  if ! stop_service scheduler || ! stop_service worker; then
    restore || true
    die "Belzakupki suspension failed; deployment was not started"
  fi
  trap - INT TERM
  echo "Belzakupki worker/scheduler are safely suspended for this deployment"
}

case "${ACTION}" in
  enabled) enabled_status ;;
  prepare) prepare ;;
  restore) restore ;;
  *) die "usage: $0 enabled|prepare|restore" ;;
esac
