#!/usr/bin/env bash
# Client-side values are shell-quoted deliberately before they enter SSH commands.
# shellcheck disable=SC2029
set -euo pipefail
umask 077

OPERATION="${1:-}"
NODE_HOST="${API_NODE_HOST:-}"
NODE_USER="${API_NODE_USER:-root}"
PROJECT_DIR="${API_NODE_PROJECT_DIR:-}"
COMPOSE_SOURCE="${API_NODE_COMPOSE_SOURCE:-}"
PROXY_MODE="${API_NODE_PROXY_MODE:-host_nginx}"
EXPECTED_ROLE="${API_EXPECTED_PATRONI_ROLE:-}"
PITR_MAINTENANCE_MARKER="${API_PITR_MAINTENANCE_MARKER:-/run/mvn-postgres-pitr-maintenance}"
BACKEND_IMAGE="${BACKEND_IMAGE:-}"
SSH_PRIVATE_KEY="${SSH_PRIVATE_KEY:-}"
SSH_HOST_KEY_SOURCE="${API_NODE_SSH_HOST_KEY_SOURCE:-}"
KEY_PATH="${RUNNER_TEMP:-/tmp}/mvn-patroni-${GITHUB_RUN_ID:-local}-${GITHUB_JOB:-job}.key"
KNOWN_HOSTS_PATH="${KEY_PATH}.known_hosts"
ROLE_AGENT_SOURCE="scripts/ha/patroni_role_agent.py"
ROLE_AGENT_TARGET="/usr/local/sbin/mvn-patroni-role-agent"
ROLE_COMPOSE_RUNTIME_SOURCE="scripts/ha/patroni_compose_runtime.py"
ROLE_COMPOSE_RUNTIME_TARGET="/usr/local/sbin/patroni_compose_runtime.py"
ROLE_AGENT_CONFIG_SOURCE="scripts/ha/patroni_role_agent_config.py"
ROLE_AGENT_CONFIG_TARGET="/usr/local/sbin/patroni_role_agent_config.py"
ROLE_IDENTITY_SOURCE="scripts/ha/patroni_local_identity.py"
ROLE_IDENTITY_TARGET="/usr/local/sbin/patroni_local_identity.py"
ROLE_UNIT_SOURCE="deploy/ha/patroni/mvn-patroni-role-agent.service"
ROLE_UNIT_TARGET="/etc/systemd/system/mvn-patroni-role-agent.service"
ROLE_AGENT_UNIT="mvn-patroni-role-agent.service"
CANDIDATE_RUNNER_SOURCE="scripts/ha/run_patroni_candidate_transaction.sh"
DEPLOY_LOCK_HELPER_SOURCE="scripts/ha/safe_deploy_lock.py"
DEPLOY_CAPACITY_HELPER_SOURCE="scripts/ha/require_deploy_capacity.sh"
COMMUNICATIONS_WORKER_RELEASE_HELPER_SOURCE="scripts/ha/communications_worker_release_contract.sh"
PATRONI_COMMUNICATIONS_CANDIDATE_LIFECYCLE_SOURCE="scripts/ha/patroni_communications_candidate_lifecycle.sh"
PATRONI_ROLE_AGENT_CANDIDATE_ASSETS_SOURCE="scripts/ha/patroni_role_agent_candidate_assets.sh"
DEPLOY_LOCK_HELPER_SHA256="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "${DEPLOY_LOCK_HELPER_SOURCE}")"
DB_CONTRACT_HELPER_SOURCE="scripts/ha/patroni_compose_db_contract.py"
TRANSACTION_SOURCE="scripts/compose_candidate_transaction.sh"
BUNDLE_VERIFIER_SOURCE="scripts/ha/verify_patroni_remote_bundle.py"
VOICE_ENV_SYNC_SOURCE="scripts/ha/sync_bot_voice_env.py"
BOT_VOICE_TRANSCRIPTION_API_KEY="${BOT_VOICE_TRANSCRIPTION_API_KEY:-}"
REMOTE_BUNDLE_DIR=""
DEPLOY_CAPACITY_PROFILE=primary
CANONICAL_REMOTE_COMPOSE_FILE="docker-compose.patroni.yml"

log() {
  printf '[patroni-remote][%s] %s\n' "$1" "$2"
}

usage() {
  echo "usage: run_patroni_node_remote.sh probe|migrate|deploy|verify" >&2
}

quote() {
  printf '%q' "$1"
}

cleanup() {
  if [[ -n "${REMOTE_BUNDLE_DIR}" ]]; then
    ssh "${SSH_OPTS[@]}" "${REMOTE}" \
      "rm -rf -- $(quote "${REMOTE_BUNDLE_DIR}")" \
      >/dev/null 2>&1 || true
  fi
  rm -f "${KEY_PATH}" "${KNOWN_HOSTS_PATH}"
}

[[ "${OPERATION}" == "probe" || "${OPERATION}" == "migrate" \
  || "${OPERATION}" == "deploy" || "${OPERATION}" == "verify" ]] || {
  usage
  exit 2
}
[[ -n "${NODE_HOST}" && -n "${NODE_USER}" ]] || {
  log error "API_NODE_HOST and API_NODE_USER are required"
  exit 1
}
[[ -n "${SSH_PRIVATE_KEY}" ]] || {
  log error "SSH_PRIVATE_KEY is required"
  exit 1
}
[[ -f "${SSH_HOST_KEY_SOURCE}" && ! -L "${SSH_HOST_KEY_SOURCE}" ]] || {
  log error "tracked API_NODE_SSH_HOST_KEY_SOURCE is required"
  exit 1
}
[[ "${NODE_HOST}" =~ ^[A-Za-z0-9][A-Za-z0-9._:-]*$ ]] || {
  log error "API_NODE_HOST contains unsupported characters"
  exit 1
}
[[ "${NODE_USER}" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]] || {
  log error "API_NODE_USER contains unsupported characters"
  exit 1
}
if [[ "${OPERATION}" == "migrate" || "${OPERATION}" == "deploy" ]]; then
  [[ -n "${PROJECT_DIR}" && -f "${COMPOSE_SOURCE}" ]] || {
    log error "project directory and tracked compose source are required"
    exit 1
  }
  [[ "${BACKEND_IMAGE}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]] || {
    log error "BACKEND_IMAGE must be immutable"
    exit 1
  }
  [[ -n "${BOT_VOICE_TRANSCRIPTION_API_KEY}" ]] || {
    log error "BOT_VOICE_TRANSCRIPTION_API_KEY is required"
    exit 1
  }
fi
if [[ "${PROJECT_DIR}" == "/opt/mvn-reserve" ]]; then
  DEPLOY_CAPACITY_PROFILE=reserve
fi
if [[ "${OPERATION}" == "deploy" || "${OPERATION}" == "verify" ]]; then
  [[ "${EXPECTED_ROLE}" == "primary" || "${EXPECTED_ROLE}" == "standby" ]] || {
    log error "API_EXPECTED_PATRONI_ROLE must be primary or standby"
    exit 1
  }
fi
if [[ "${OPERATION}" == "verify" ]]; then
  [[ -n "${PROJECT_DIR}" ]] || {
    log error "API_NODE_PROJECT_DIR is required for runtime verification"
    exit 1
  }
  [[ "${BACKEND_IMAGE}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]] || {
    log error "BACKEND_IMAGE must be immutable"
    exit 1
  }
fi
if [[ "${OPERATION}" == "deploy" ]]; then
  [[ "${PROXY_MODE}" == "host_nginx" || "${PROXY_MODE}" == "container_nginx" ]] || {
    log error "API_NODE_PROXY_MODE must be host_nginx or container_nginx"
    exit 1
  }
  [[ -f "${ROLE_AGENT_SOURCE}" && ! -L "${ROLE_AGENT_SOURCE}" \
    && -f "${ROLE_COMPOSE_RUNTIME_SOURCE}" && ! -L "${ROLE_COMPOSE_RUNTIME_SOURCE}" \
    && -f "${ROLE_AGENT_CONFIG_SOURCE}" && ! -L "${ROLE_AGENT_CONFIG_SOURCE}" \
    && -f "${ROLE_IDENTITY_SOURCE}" && ! -L "${ROLE_IDENTITY_SOURCE}" \
    && -f "${ROLE_UNIT_SOURCE}" && ! -L "${ROLE_UNIT_SOURCE}" ]] || {
    log error "role agent source bundle is incomplete"
    exit 1
  }
fi
if [[ "${OPERATION}" == "migrate" || "${OPERATION}" == "deploy" ]]; then
  [[ -f "${CANDIDATE_RUNNER_SOURCE}" && -f "${TRANSACTION_SOURCE}" \
    && -f "${DEPLOY_CAPACITY_HELPER_SOURCE}" \
    && -f "${COMMUNICATIONS_WORKER_RELEASE_HELPER_SOURCE}" \
    && ! -L "${COMMUNICATIONS_WORKER_RELEASE_HELPER_SOURCE}" \
    && -f "${PATRONI_COMMUNICATIONS_CANDIDATE_LIFECYCLE_SOURCE}" \
    && ! -L "${PATRONI_COMMUNICATIONS_CANDIDATE_LIFECYCLE_SOURCE}" \
    && -f "${PATRONI_ROLE_AGENT_CANDIDATE_ASSETS_SOURCE}" \
    && ! -L "${PATRONI_ROLE_AGENT_CANDIDATE_ASSETS_SOURCE}" \
    && -f "${DEPLOY_LOCK_HELPER_SOURCE}" && -f "${BUNDLE_VERIFIER_SOURCE}" \
    && -f "${VOICE_ENV_SYNC_SOURCE}" && ! -L "${VOICE_ENV_SYNC_SOURCE}" ]] || {
    log error "compose candidate transaction scripts are missing"
    exit 1
  }
fi
if [[ "${OPERATION}" == "deploy" ]]; then
  [[ -f "${DB_CONTRACT_HELPER_SOURCE}" \
    && ! -L "${DB_CONTRACT_HELPER_SOURCE}" ]] || {
    log error "Patroni db contract helper is missing or unsafe"
    exit 1
  }
fi

required_commands=(ssh ssh-keygen)
if [[ "${OPERATION}" == "migrate" || "${OPERATION}" == "deploy" ]]; then
  required_commands+=(scp)
fi
for command in "${required_commands[@]}"; do
  command -v "${command}" >/dev/null 2>&1 || {
    log error "required command is missing: ${command}"
    exit 1
  }
done

trap cleanup EXIT
printf '%s\n' "${SSH_PRIVATE_KEY}" > "${KEY_PATH}"
chmod 600 "${KEY_PATH}"
: > "${KNOWN_HOSTS_PATH}"
host_key_lines=()
while IFS= read -r host_key_line || [[ -n "${host_key_line}" ]]; do
  host_key_lines+=("${host_key_line}")
done < "${SSH_HOST_KEY_SOURCE}"
[[ "${#host_key_lines[@]}" -eq 1 ]] || {
  log error "pinned SSH host key source must contain exactly one line"
  exit 1
}
read -r host_key_type host_key_value host_key_extra <<< "${host_key_lines[0]}"
[[ "${host_key_type}" == "ssh-ed25519" \
  && "${host_key_value}" =~ ^[A-Za-z0-9+/]+={0,2}$ \
  && -z "${host_key_extra:-}" ]] || {
  log error "pinned SSH host key must contain one Ed25519 public key"
  exit 1
}
ssh-keygen -lf "${SSH_HOST_KEY_SOURCE}" -E sha256 >/dev/null || {
  log error "pinned SSH host key is invalid"
  exit 1
}
printf '%s %s %s\n' \
  "${NODE_HOST}" "${host_key_type}" "${host_key_value}" \
  > "${KNOWN_HOSTS_PATH}"
chmod 600 "${KNOWN_HOSTS_PATH}"

SSH_OPTS=(
  -F /dev/null
  -i "${KEY_PATH}"
  -o BatchMode=yes
  -o IdentitiesOnly=yes
  -o StrictHostKeyChecking=yes
  -o GlobalKnownHostsFile=/dev/null
  -o "UserKnownHostsFile=${KNOWN_HOSTS_PATH}"
  -o HostKeyAlgorithms=ssh-ed25519
  -o UpdateHostKeys=no
  -o ConnectTimeout=20
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=3
)
REMOTE="${NODE_USER}@${NODE_HOST}"

if [[ "${OPERATION}" == "probe" ]]; then
  role="$(ssh "${SSH_OPTS[@]}" "${REMOTE}" \
    "if test -e $(quote "${PITR_MAINTENANCE_MARKER}") || test -L $(quote "${PITR_MAINTENANCE_MARKER}"); then echo 'PITR release maintenance is active; refusing deployment probe' >&2; exit 75; fi; curl -fsS --max-time 5 http://127.0.0.1:8008/patroni | python3 -c 'import json,sys; p=json.load(sys.stdin); assert p.get(\"state\")==\"running\"; r=str(p.get(\"role\") or \"\").lower(); m={\"leader\":\"primary\",\"master\":\"primary\",\"primary\":\"primary\",\"replica\":\"standby\",\"standby\":\"standby\"}; n=m.get(r); n or sys.exit(1); print(n)'")"
  [[ "${role}" == "primary" || "${role}" == "standby" ]] || {
    log error "invalid Patroni role from ${NODE_HOST}: ${role}"
    exit 1
  }
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    printf 'role=%s\n' "${role}" >> "${GITHUB_OUTPUT}"
  fi
  log probe "${NODE_HOST} role=${role}"
  exit 0
fi

if [[ "${OPERATION}" == "verify" ]]; then
  verify_config_code='
import json
import sys

service_name, app_name, expected_image = sys.argv[1:]
payload = json.load(sys.stdin)
services = payload.get("services") or {}
worker = services.get(service_name)
app = services.get(app_name)
if not isinstance(worker, dict) or not isinstance(app, dict):
    raise SystemExit(1)
if worker.get("image") != expected_image or app.get("image") != expected_image:
    raise SystemExit(1)
environment = worker.get("environment") or {}
if not isinstance(environment, dict):
    raise SystemExit(1)
for key in (
    "COMMUNICATIONS_WORKER_ENABLED",
    "COMMUNICATIONS_WORKER_ALLOW_ALL_MODE",
):
    if str(environment.get(key, "")).lower() != "false":
        raise SystemExit(1)
'
  verify_worker_runtime_code='
import os
import sys

expected_role = sys.argv[1]
valid = (
    os.environ.get("APP_ROLE") == expected_role
    and os.environ.get("COMMUNICATIONS_WORKER_ENABLED", "").lower() == "false"
    and os.environ.get("COMMUNICATIONS_WORKER_ALLOW_ALL_MODE", "").lower() == "false"
)
raise SystemExit(0 if valid else 1)
'
  verify_canary_code='
import re
import sys

expected_role = sys.argv[1]
lines = sys.stdin.read().splitlines()
receipt = f"patroni_role_agent_once_status=verified role={expected_role}"
valid = lines == [receipt]
if len(lines) == 2 and lines[1] == receipt:
    reconciled = re.fullmatch(
        r"patroni_role_agent_status=reconciled "
        r"role=(primary|standby) "
        r"app_service=[A-Za-z0-9_.-]+ "
        r"reasons=(?:[a-z0-9_]+(?:,[a-z0-9_]+)*)? "
        r"actions=(?:[a-z0-9_]+(?:,[a-z0-9_]+)*)?",
        lines[0],
    )
    valid = reconciled is not None and reconciled.group(1) == expected_role
raise SystemExit(0 if valid else 1)
'
  verify_role_code='
import json
import sys

payload = json.load(sys.stdin)
if payload.get("state") != "running":
    raise SystemExit(1)
role = str(payload.get("role") or "").lower()
mapping = {
    "leader": "primary",
    "master": "primary",
    "primary": "primary",
    "replica": "standby",
    "standby": "standby",
}
normalized = mapping.get(role)
if normalized is None:
    raise SystemExit(1)
print(normalized)
'
  verified="$(
    ssh "${SSH_OPTS[@]}" "${REMOTE}" "
      set -euo pipefail
      if test -e $(quote "${PITR_MAINTENANCE_MARKER}") \
        || test -L $(quote "${PITR_MAINTENANCE_MARKER}"); then
        echo 'PITR release maintenance is active; refusing runtime verification' >&2
        exit 75
      fi
      role=\$(curl -fsS --max-time 5 http://127.0.0.1:8008/patroni \
        | python3 -c 'import json,sys; p=json.load(sys.stdin); assert p.get(\"state\")==\"running\"; r=str(p.get(\"role\") or \"\").lower(); m={\"leader\":\"primary\",\"master\":\"primary\",\"primary\":\"primary\",\"replica\":\"standby\",\"standby\":\"standby\"}; n=m.get(r); n or sys.exit(1); print(n)')
      test \"\${role}\" = $(quote "${EXPECTED_ROLE}")
      cd $(quote "${PROJECT_DIR}")
      test -f ${CANONICAL_REMOTE_COMPOSE_FILE}
      test ! -L ${CANONICAL_REMOTE_COMPOSE_FILE}
      active_service=app
      if test -f .active-api-slot; then
        slot=\$(tr -d '\\r\\n' < .active-api-slot)
        case \"\${slot}\" in
          blue|green) active_service=\"app-\${slot}\" ;;
          *) exit 1 ;;
        esac
      fi
      export BACKEND_IMAGE=$(quote "${BACKEND_IMAGE}")
      docker_command=docker
      \"\${docker_command}\" compose -f ${CANONICAL_REMOTE_COMPOSE_FILE} --profile bluegreen \
        config --format json \
        | python3 -c $(quote "${verify_config_code}") \
          communications-worker \"\${active_service}\" $(quote "${BACKEND_IMAGE}")
      set -- \$(\"\${docker_command}\" compose -f ${CANONICAL_REMOTE_COMPOSE_FILE} \
        --profile bluegreen ps -q \"\${active_service}\")
      test \"\$#\" -eq 1
      app_id=\"\$1\"
      set -- \$(\"\${docker_command}\" compose -f ${CANONICAL_REMOTE_COMPOSE_FILE} \
        --profile bluegreen ps -q communications-worker)
      test \"\$#\" -eq 1
      worker_id=\"\$1\"
      test \"\$(\"\${docker_command}\" inspect --format '{{.Config.Image}}|{{.State.Running}}' \"\${app_id}\")\" \
        = $(quote "${BACKEND_IMAGE}|true")
      test \"\$(\"\${docker_command}\" inspect --format '{{.Config.Image}}|{{.State.Running}}' \"\${worker_id}\")\" \
        = $(quote "${BACKEND_IMAGE}|true")
      if test -e .ha-communications-worker-release-fenced \
        || test -L .ha-communications-worker-release-fenced; then
        exit 1
      fi
      if ! \"\${docker_command}\" compose -f ${CANONICAL_REMOTE_COMPOSE_FILE} \
        --profile bluegreen exec -T communications-worker \
        python3 -c $(quote "${verify_worker_runtime_code}") \"\${role}\" >/dev/null; then
        exit 1
      fi
      if ! systemctl is-active --quiet mvn-patroni-role-agent.service; then
        exit 1
      fi
      role_agent_pid_before=\$(systemctl show --property=MainPID --value \
        mvn-patroni-role-agent.service)
      role_agent_restarts_before=\$(systemctl show --property=NRestarts --value \
        mvn-patroni-role-agent.service)
      case \"\${role_agent_pid_before}\" in
        ''|*[!0-9]*|0) exit 1 ;;
      esac
      case \"\${role_agent_restarts_before}\" in
        ''|*[!0-9]*) exit 1 ;;
      esac
      sleep 2
      if ! systemctl is-active --quiet mvn-patroni-role-agent.service; then
        exit 1
      fi
      role_agent_pid_after=\$(systemctl show --property=MainPID --value \
        mvn-patroni-role-agent.service)
      role_agent_restarts_after=\$(systemctl show --property=NRestarts --value \
        mvn-patroni-role-agent.service)
      if test \"\${role_agent_pid_after}\" != \"\${role_agent_pid_before}\" \
        || test \"\${role_agent_restarts_after}\" != \"\${role_agent_restarts_before}\"; then
        exit 1
      fi
      role_agent_canary_passed=false
      for canary_attempt in 1 2 3; do
        role_agent_canary_rc=0
        role_agent_canary_output=\$(
          timeout 120 $(quote "${ROLE_AGENT_TARGET}") --once 2>/dev/null
        ) || role_agent_canary_rc=\$?
        if test \"\${role_agent_canary_rc}\" -eq 0 \
          && printf '%s' \"\${role_agent_canary_output}\" \
            | python3 -c $(quote "${verify_canary_code}") \"\${role}\"; then
          role_agent_canary_passed=true
          break
        fi
        if test \"\${role_agent_canary_rc}\" -eq 75 \
          && test \"\${role_agent_canary_output}\" \
            = 'patroni_role_agent_status=deferred reason=deployment_lock_busy' \
          && test \"\${canary_attempt}\" -lt 3; then
          sleep 1
          continue
        fi
        exit 1
      done
      test \"\${role_agent_canary_passed}\" = true
      final_role=\$(curl -fsS --max-time 5 http://127.0.0.1:8008/patroni \
        | python3 -c $(quote "${verify_role_code}"))
      if test \"\${final_role}\" != \"\${role}\" \
        || test \"\${final_role}\" != $(quote "${EXPECTED_ROLE}"); then
        exit 1
      fi
      if test -e .ha-communications-worker-release-fenced \
        || test -L .ha-communications-worker-release-fenced; then
        exit 1
      fi
      set -- \$(\"\${docker_command}\" compose -f ${CANONICAL_REMOTE_COMPOSE_FILE} \
        --profile bluegreen ps -q communications-worker)
      test \"\$#\" -eq 1
      worker_id=\"\$1\"
      test \"\$(\"\${docker_command}\" inspect --format '{{.Config.Image}}|{{.State.Running}}' \"\${worker_id}\")\" \
        = $(quote "${BACKEND_IMAGE}|true")
      if ! \"\${docker_command}\" compose -f ${CANONICAL_REMOTE_COMPOSE_FILE} \
        --profile bluegreen exec -T communications-worker \
        python3 -c $(quote "${verify_worker_runtime_code}") \"\${final_role}\" >/dev/null; then
        exit 1
      fi
      if ! systemctl is-active --quiet mvn-patroni-role-agent.service; then
        exit 1
      fi
      if test \"\$(systemctl show --property=MainPID --value \
          mvn-patroni-role-agent.service)\" != \"\${role_agent_pid_before}\" \
        || test \"\$(systemctl show --property=NRestarts --value \
          mvn-patroni-role-agent.service)\" != \"\${role_agent_restarts_before}\"; then
        exit 1
      fi
      printf 'verified:%s\\n' \"\${role}\"
    "
  )"
  [[ "${verified}" == "verified:${EXPECTED_ROLE}" ]] || {
    log error "runtime postcondition verification failed on ${NODE_HOST}"
    exit 1
  }
  log verify "${NODE_HOST} role=${EXPECTED_ROLE} API/worker parity confirmed"
  exit 0
fi

ssh "${SSH_OPTS[@]}" "${REMOTE}" \
  "test -d $(quote "${PROJECT_DIR}"); if test -e $(quote "${PITR_MAINTENANCE_MARKER}") || test -L $(quote "${PITR_MAINTENANCE_MARKER}"); then echo 'PITR release maintenance is active; refusing remote release staging' >&2; exit 75; fi"
candidate_id="$(printf '%s' "${GITHUB_RUN_ID:-local}-${GITHUB_JOB:-job}-${OPERATION}-$$" | tr -c 'A-Za-z0-9_.-' '-')"
REMOTE_COMPOSE_FILE="docker-compose.patroni.candidate.${candidate_id}.yml"
REMOTE_BUNDLE_DIR="$(
  ssh "${SSH_OPTS[@]}" "${REMOTE}" \
    "umask 077; mktemp -d /tmp/mvn-patroni-release.XXXXXXXX"
)"
[[ "${REMOTE_BUNDLE_DIR}" =~ ^/tmp/mvn-patroni-release\.[A-Za-z0-9]{8}$ ]] || {
  log error "remote Patroni release bundle directory is invalid"
  exit 1
}
BUNDLE_SOURCES=(
  "${COMPOSE_SOURCE}"
  scripts/ha/run_patroni_migrations.sh
  scripts/ha/deploy_patroni_api_node.sh
  scripts/deploy_backend_blue_green.sh
  scripts/deploy_backend_blue_green_safety.sh
  scripts/prepare_google_oauth_token_dir.sh
  scripts/reconcile_backend_compose_runtime.sh
  "${CANDIDATE_RUNNER_SOURCE}"
  "${DEPLOY_LOCK_HELPER_SOURCE}"
  "${DEPLOY_CAPACITY_HELPER_SOURCE}"
  "${COMMUNICATIONS_WORKER_RELEASE_HELPER_SOURCE}"
  "${PATRONI_COMMUNICATIONS_CANDIDATE_LIFECYCLE_SOURCE}"
  "${PATRONI_ROLE_AGENT_CANDIDATE_ASSETS_SOURCE}"
  "${TRANSACTION_SOURCE}"
  "${VOICE_ENV_SYNC_SOURCE}"
)
if [[ "${OPERATION}" == "deploy" ]]; then
  BUNDLE_SOURCES+=(
    "${DB_CONTRACT_HELPER_SOURCE}"
    "${ROLE_AGENT_SOURCE}"
    "${ROLE_COMPOSE_RUNTIME_SOURCE}"
    "${ROLE_AGENT_CONFIG_SOURCE}"
    "${ROLE_IDENTITY_SOURCE}"
    "${ROLE_UNIT_SOURCE}"
  )
  if [[ "${PROXY_MODE}" == "container_nginx" ]]; then
    BUNDLE_SOURCES+=(
      deploy/ha/proxy/nginx.conf
      deploy/ha/proxy/upstream.conf
    )
  fi
fi
BUNDLE_MANIFEST_B64="$(python3 "${BUNDLE_VERIFIER_SOURCE}" manifest "${BUNDLE_SOURCES[@]}")"
BUNDLE_VERIFIER_CODE="$(<"${BUNDLE_VERIFIER_SOURCE}")"
ROLE_AGENT_REMOTE="${REMOTE_BUNDLE_DIR}/patroni_role_agent.py"
ROLE_COMPOSE_RUNTIME_REMOTE="${REMOTE_BUNDLE_DIR}/patroni_compose_runtime.py"
ROLE_AGENT_CONFIG_REMOTE="${REMOTE_BUNDLE_DIR}/patroni_role_agent_config.py"
ROLE_IDENTITY_REMOTE="${REMOTE_BUNDLE_DIR}/patroni_local_identity.py"
ROLE_UNIT_REMOTE="${REMOTE_BUNDLE_DIR}/mvn-patroni-role-agent.service"
DB_CONTRACT_HELPER_REMOTE="${REMOTE_BUNDLE_DIR}/patroni_compose_db_contract.py"
VOICE_ENV_SYNC_REMOTE="${REMOTE_BUNDLE_DIR}/sync_bot_voice_env.py"
COMMUNICATIONS_WORKER_RELEASE_HELPER_REMOTE="${REMOTE_BUNDLE_DIR}/communications_worker_release_contract.sh"
PATRONI_COMMUNICATIONS_CANDIDATE_LIFECYCLE_REMOTE="${REMOTE_BUNDLE_DIR}/patroni_communications_candidate_lifecycle.sh"
PATRONI_ROLE_AGENT_CANDIDATE_ASSETS_REMOTE="${REMOTE_BUNDLE_DIR}/patroni_role_agent_candidate_assets.sh"
REMOTE_COMPOSE_SOURCE="${REMOTE_BUNDLE_DIR}/$(basename "${COMPOSE_SOURCE}")"
scp "${SSH_OPTS[@]}" "${BUNDLE_SOURCES[@]}" "${REMOTE}:${REMOTE_BUNDLE_DIR}/"

proxy_env="API_PROXY_MODE=$(quote "${PROXY_MODE}")"
if [[ "${PROXY_MODE}" == "container_nginx" ]]; then
  proxy_env+=" API_NGINX_UPSTREAM_FILE=$(quote "${PROJECT_DIR}/api-proxy/upstream.conf")"
  proxy_env+=" API_PROXY_CONFIG_FILE=$(quote "${PROJECT_DIR}/api-proxy/nginx.conf")"
  proxy_env+=" API_LEGACY_PORT=18000"
fi

log "${OPERATION}" "running ${OPERATION} on ${NODE_HOST}"
printf '%s\n%s\n' "${GHCR_PAT:-}" "${BOT_VOICE_TRANSCRIPTION_API_KEY}" | ssh "${SSH_OPTS[@]}" "${REMOTE}" "
  set -euo pipefail
  IFS= read -r GHCR_PAT
  IFS= read -r BOT_VOICE_TRANSCRIPTION_API_KEY
  export GHCR_PAT
  trap $(quote "rm -rf -- ${REMOTE_BUNDLE_DIR}") EXIT
  python3 -I -c $(quote "${BUNDLE_VERIFIER_CODE}") verify \
    $(quote "${REMOTE_BUNDLE_DIR}") $(quote "${BUNDLE_MANIFEST_B64}")
  chmod 0755 $(quote "${REMOTE_BUNDLE_DIR}")/*.sh \
    $(quote "${REMOTE_BUNDLE_DIR}/safe_deploy_lock.py")
  printf '%s' \"\${BOT_VOICE_TRANSCRIPTION_API_KEY}\" | \
    python3 -I $(quote "${VOICE_ENV_SYNC_REMOTE}") \
      --env-file $(quote "${PROJECT_DIR}/.env")
  unset BOT_VOICE_TRANSCRIPTION_API_KEY
  API_PROJECT_DIR=$(quote "${PROJECT_DIR}") \
  API_EXPECTED_PATRONI_ROLE=$(quote "${EXPECTED_ROLE}") \
  API_READY_URL=http://127.0.0.1:18080/api/ready \
  API_HEALTH_URL=http://127.0.0.1:18080/api/health \
  API_INTERNAL_PROXY_PORT=18080 \
  API_BLUE_GREEN_SCRIPT=$(quote "${REMOTE_BUNDLE_DIR}/deploy_backend_blue_green.sh") \
  API_BLUE_GREEN_SAFETY_HELPER=$(quote "${REMOTE_BUNDLE_DIR}/deploy_backend_blue_green_safety.sh") \
  GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT=$(quote "${REMOTE_BUNDLE_DIR}/prepare_google_oauth_token_dir.sh") \
  API_RECONCILE_SCRIPT=$(quote "${REMOTE_BUNDLE_DIR}/reconcile_backend_compose_runtime.sh") \
  API_PUBLIC_READY_URL=https://api.mvn.by/api/ready \
  BACKEND_IMAGE=$(quote "${BACKEND_IMAGE}") \
  GITHUB_ACTOR=$(quote "${GITHUB_ACTOR:-github-actions}") \
  PATRONI_CANDIDATE_OPERATION=$(quote "${OPERATION}") \
  PATRONI_CANONICAL_COMPOSE_FILE=$(quote "${PROJECT_DIR}/${CANONICAL_REMOTE_COMPOSE_FILE}") \
  PATRONI_CANDIDATE_COMPOSE_FILE=$(quote "${PROJECT_DIR}/${REMOTE_COMPOSE_FILE}") \
  PATRONI_CANDIDATE_COMPOSE_SOURCE=$(quote "${REMOTE_COMPOSE_SOURCE}") \
  PATRONI_MIGRATION_SCRIPT=$(quote "${REMOTE_BUNDLE_DIR}/run_patroni_migrations.sh") \
  PATRONI_DEPLOY_SCRIPT=$(quote "${REMOTE_BUNDLE_DIR}/deploy_patroni_api_node.sh") \
  PATRONI_PROXY_CONFIG_SOURCE=$(quote "${REMOTE_BUNDLE_DIR}/nginx.conf") \
  PATRONI_PROXY_UPSTREAM_SOURCE=$(quote "${REMOTE_BUNDLE_DIR}/upstream.conf") \
  COMPOSE_CANDIDATE_TRANSACTION_SCRIPT=$(quote "${REMOTE_BUNDLE_DIR}/compose_candidate_transaction.sh") \
  PATRONI_ROLE_AGENT_SOURCE=$(quote "${ROLE_AGENT_REMOTE}") \
  PATRONI_ROLE_AGENT_TARGET=$(quote "${ROLE_AGENT_TARGET}") \
  PATRONI_ROLE_COMPOSE_RUNTIME_SOURCE=$(quote "${ROLE_COMPOSE_RUNTIME_REMOTE}") \
  PATRONI_ROLE_COMPOSE_RUNTIME_TARGET=$(quote "${ROLE_COMPOSE_RUNTIME_TARGET}") \
  PATRONI_ROLE_AGENT_CONFIG_SOURCE=$(quote "${ROLE_AGENT_CONFIG_REMOTE}") \
  PATRONI_ROLE_AGENT_CONFIG_TARGET=$(quote "${ROLE_AGENT_CONFIG_TARGET}") \
  PATRONI_ROLE_IDENTITY_SOURCE=$(quote "${ROLE_IDENTITY_REMOTE}") \
  PATRONI_ROLE_IDENTITY_TARGET=$(quote "${ROLE_IDENTITY_TARGET}") \
  PATRONI_ROLE_UNIT_SOURCE=$(quote "${ROLE_UNIT_REMOTE}") \
  PATRONI_ROLE_UNIT_TARGET=$(quote "${ROLE_UNIT_TARGET}") \
  PATRONI_DB_CONTRACT_HELPER=$(quote "${DB_CONTRACT_HELPER_REMOTE}") \
  PATRONI_ROLE_AGENT_UNIT=$(quote "${ROLE_AGENT_UNIT}") \
  API_DEPLOY_LOCK_HELPER=$(quote "${REMOTE_BUNDLE_DIR}/safe_deploy_lock.py") \
  API_DEPLOY_CAPACITY_HELPER=$(quote "${REMOTE_BUNDLE_DIR}/require_deploy_capacity.sh") \
  API_DEPLOY_CAPACITY_PROFILE=$(quote "${DEPLOY_CAPACITY_PROFILE}") \
  COMMUNICATIONS_WORKER_RELEASE_HELPER=$(quote "${COMMUNICATIONS_WORKER_RELEASE_HELPER_REMOTE}") \
  PATRONI_COMMUNICATIONS_CANDIDATE_LIFECYCLE=$(quote "${PATRONI_COMMUNICATIONS_CANDIDATE_LIFECYCLE_REMOTE}") \
  PATRONI_ROLE_AGENT_CANDIDATE_ASSETS=$(quote "${PATRONI_ROLE_AGENT_CANDIDATE_ASSETS_REMOTE}") \
  API_DEPLOY_LOCK_HELPER_SHA256=$(quote "${DEPLOY_LOCK_HELPER_SHA256}") \
  ${proxy_env} \
  bash $(quote "${REMOTE_BUNDLE_DIR}/run_patroni_candidate_transaction.sh")
"
REMOTE_BUNDLE_DIR=""
log "done" "${OPERATION} completed on ${NODE_HOST}"
