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
BACKEND_IMAGE="${BACKEND_IMAGE:-}"
SSH_PRIVATE_KEY="${SSH_PRIVATE_KEY:-}"
SSH_HOST_KEY_SOURCE="${API_NODE_SSH_HOST_KEY_SOURCE:-}"
KEY_PATH="${RUNNER_TEMP:-/tmp}/mvn-patroni-${GITHUB_RUN_ID:-local}-${GITHUB_JOB:-job}.key"
KNOWN_HOSTS_PATH="${KEY_PATH}.known_hosts"
ROLE_AGENT_SOURCE="scripts/ha/patroni_role_agent.py"
ROLE_AGENT_REMOTE="/tmp/mvn-patroni-role-agent-${GITHUB_RUN_ID:-local}-${GITHUB_JOB:-job}"
ROLE_AGENT_TARGET="/usr/local/sbin/mvn-patroni-role-agent"
ROLE_AGENT_UNIT="mvn-patroni-role-agent.service"
CANDIDATE_RUNNER_SOURCE="scripts/ha/run_patroni_candidate_transaction.sh"
TRANSACTION_SOURCE="scripts/compose_candidate_transaction.sh"

log() {
  printf '[patroni-remote][%s] %s\n' "$1" "$2"
}

usage() {
  echo "usage: run_patroni_node_remote.sh probe|migrate|deploy" >&2
}

quote() {
  printf '%q' "$1"
}

[[ "${OPERATION}" == "probe" || "${OPERATION}" == "migrate" || "${OPERATION}" == "deploy" ]] || {
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
if [[ "${OPERATION}" != "probe" ]]; then
  [[ -n "${PROJECT_DIR}" && -f "${COMPOSE_SOURCE}" ]] || {
    log error "project directory and tracked compose source are required"
    exit 1
  }
  [[ "${BACKEND_IMAGE}" =~ (@sha256:[0-9a-f]{64}|:[0-9a-f]{40})$ ]] || {
    log error "BACKEND_IMAGE must be immutable"
    exit 1
  }
fi
if [[ "${OPERATION}" == "deploy" ]]; then
  [[ "${EXPECTED_ROLE}" == "primary" || "${EXPECTED_ROLE}" == "standby" ]] || {
    log error "API_EXPECTED_PATRONI_ROLE must be primary or standby"
    exit 1
  }
  [[ "${PROXY_MODE}" == "host_nginx" || "${PROXY_MODE}" == "container_nginx" ]] || {
    log error "API_NODE_PROXY_MODE must be host_nginx or container_nginx"
    exit 1
  }
  [[ -f "${ROLE_AGENT_SOURCE}" ]] || {
    log error "role agent source is missing: ${ROLE_AGENT_SOURCE}"
    exit 1
  }
fi
if [[ "${OPERATION}" != "probe" ]]; then
  [[ -f "${CANDIDATE_RUNNER_SOURCE}" && -f "${TRANSACTION_SOURCE}" ]] || {
    log error "compose candidate transaction scripts are missing"
    exit 1
  }
fi

required_commands=(ssh ssh-keygen)
if [[ "${OPERATION}" != "probe" ]]; then
  required_commands+=(scp)
fi
for command in "${required_commands[@]}"; do
  command -v "${command}" >/dev/null 2>&1 || {
    log error "required command is missing: ${command}"
    exit 1
  }
done

trap 'rm -f "${KEY_PATH}" "${KNOWN_HOSTS_PATH}"' EXIT
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
    "curl -fsS --max-time 5 http://127.0.0.1:8008/patroni | python3 -c 'import json,sys; p=json.load(sys.stdin); assert p.get(\"state\")==\"running\"; r=str(p.get(\"role\") or \"\").lower(); m={\"leader\":\"primary\",\"master\":\"primary\",\"primary\":\"primary\",\"replica\":\"standby\",\"standby\":\"standby\"}; n=m.get(r); n or sys.exit(1); print(n)'")"
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

ssh "${SSH_OPTS[@]}" "${REMOTE}" "mkdir -p $(quote "${PROJECT_DIR}")"
CANONICAL_REMOTE_COMPOSE_FILE="docker-compose.patroni.yml"
candidate_id="$(printf '%s' "${GITHUB_RUN_ID:-local}-${GITHUB_JOB:-job}-${OPERATION}-$$" | tr -c 'A-Za-z0-9_.-' '-')"
REMOTE_COMPOSE_FILE="docker-compose.patroni.candidate.${candidate_id}.yml"
scp "${SSH_OPTS[@]}" "${COMPOSE_SOURCE}" \
  "${REMOTE}:${PROJECT_DIR}/${REMOTE_COMPOSE_FILE}"
scp "${SSH_OPTS[@]}" scripts/ha/run_patroni_migrations.sh \
  scripts/ha/deploy_patroni_api_node.sh scripts/deploy_backend_blue_green.sh \
  scripts/deploy_backend_blue_green_safety.sh scripts/prepare_google_oauth_token_dir.sh \
  scripts/reconcile_backend_compose_runtime.sh \
  "${CANDIDATE_RUNNER_SOURCE}" "${TRANSACTION_SOURCE}" \
  "${REMOTE}:/tmp/"
if [[ "${OPERATION}" == "deploy" ]]; then
  scp "${SSH_OPTS[@]}" "${ROLE_AGENT_SOURCE}" "${REMOTE}:${ROLE_AGENT_REMOTE}"
fi

if [[ "${PROXY_MODE}" == "container_nginx" ]]; then
  ssh "${SSH_OPTS[@]}" "${REMOTE}" "mkdir -p $(quote "${PROJECT_DIR}/api-proxy")"
  scp "${SSH_OPTS[@]}" deploy/ha/proxy/nginx.conf \
    "${REMOTE}:${PROJECT_DIR}/api-proxy/nginx.conf"
  if ! ssh "${SSH_OPTS[@]}" "${REMOTE}" "test -f $(quote "${PROJECT_DIR}/api-proxy/upstream.conf")"; then
    scp "${SSH_OPTS[@]}" deploy/ha/proxy/upstream.conf \
      "${REMOTE}:${PROJECT_DIR}/api-proxy/upstream.conf"
  fi
fi

proxy_env="API_PROXY_MODE=$(quote "${PROXY_MODE}")"
if [[ "${PROXY_MODE}" == "container_nginx" ]]; then
  proxy_env+=" API_NGINX_UPSTREAM_FILE=$(quote "${PROJECT_DIR}/api-proxy/upstream.conf")"
  proxy_env+=" API_PROXY_CONFIG_FILE=$(quote "${PROJECT_DIR}/api-proxy/nginx.conf")"
  proxy_env+=" API_LEGACY_PORT=18000"
fi

log "${OPERATION}" "running ${OPERATION} on ${NODE_HOST}"
printf '%s\n' "${GHCR_PAT:-}" | ssh "${SSH_OPTS[@]}" "${REMOTE}" "
  set -euo pipefail
  IFS= read -r GHCR_PAT
  export GHCR_PAT
  chmod 0755 /tmp/run_patroni_migrations.sh /tmp/deploy_patroni_api_node.sh /tmp/deploy_backend_blue_green.sh /tmp/deploy_backend_blue_green_safety.sh /tmp/prepare_google_oauth_token_dir.sh /tmp/reconcile_backend_compose_runtime.sh /tmp/run_patroni_candidate_transaction.sh /tmp/compose_candidate_transaction.sh
  API_PROJECT_DIR=$(quote "${PROJECT_DIR}") \
  API_EXPECTED_PATRONI_ROLE=$(quote "${EXPECTED_ROLE}") \
  API_READY_URL=http://127.0.0.1:18080/api/ready \
  API_HEALTH_URL=http://127.0.0.1:18080/api/health \
  API_INTERNAL_PROXY_PORT=18080 \
  API_BLUE_GREEN_SCRIPT=/tmp/deploy_backend_blue_green.sh \
  API_BLUE_GREEN_SAFETY_HELPER=/tmp/deploy_backend_blue_green_safety.sh \
  GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT=/tmp/prepare_google_oauth_token_dir.sh \
  API_RECONCILE_SCRIPT=/tmp/reconcile_backend_compose_runtime.sh \
  API_PUBLIC_READY_URL=https://api.mvn.by/api/ready \
  BACKEND_IMAGE=$(quote "${BACKEND_IMAGE}") \
  GITHUB_ACTOR=$(quote "${GITHUB_ACTOR:-github-actions}") \
  PATRONI_CANDIDATE_OPERATION=$(quote "${OPERATION}") \
  PATRONI_CANONICAL_COMPOSE_FILE=$(quote "${PROJECT_DIR}/${CANONICAL_REMOTE_COMPOSE_FILE}") \
  PATRONI_CANDIDATE_COMPOSE_FILE=$(quote "${PROJECT_DIR}/${REMOTE_COMPOSE_FILE}") \
  PATRONI_ROLE_AGENT_SOURCE=$(quote "${ROLE_AGENT_REMOTE}") \
  PATRONI_ROLE_AGENT_TARGET=$(quote "${ROLE_AGENT_TARGET}") \
  PATRONI_ROLE_AGENT_UNIT=$(quote "${ROLE_AGENT_UNIT}") \
  ${proxy_env} \
  bash /tmp/run_patroni_candidate_transaction.sh
"
log "done" "${OPERATION} completed on ${NODE_HOST}"
