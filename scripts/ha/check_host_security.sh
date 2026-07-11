#!/usr/bin/env bash
set -euo pipefail

EXPECTED_WG_IP="${EXPECTED_WG_IP:-${1:-}}"
HOST_LABEL="${HOST_LABEL:-${2:-$(hostname -s)}}"
EXPECTED_LISTEN_PORTS="${EXPECTED_LISTEN_PORTS:-${3:-2379,2380}}"
EXPECTED_LISTEN_PORTS="${EXPECTED_LISTEN_PORTS//,/ }"
SENSITIVE_TCP_PORTS="${SENSITIVE_TCP_PORTS:-2379 2380 5432 8008 18000 18001 18002 18080}"
FAIL2BAN_JAIL="${FAIL2BAN_JAIL:-sshd}"

failures=0

log() {
  printf '[host-security][%s] host=%s %s\n' "$1" "${HOST_LABEL}" "$2"
}

fail() {
  failures=$((failures + 1))
  log fail "$*"
}

ok() {
  log ok "$*"
}

is_port_listed() {
  local expected="$1"
  local value
  for value in ${SENSITIVE_TCP_PORTS}; do
    [[ "${value}" == "${expected}" ]] && return 0
  done
  return 1
}

[[ "${EXPECTED_WG_IP}" =~ ^10\.77\.0\.[0-9]+$ ]] || {
  log fail "EXPECTED_WG_IP must be an MVN WireGuard IPv4 address"
  exit 2
}
for value in ${EXPECTED_LISTEN_PORTS} ${SENSITIVE_TCP_PORTS}; do
  [[ "${value}" =~ ^[0-9]+$ ]] || {
    log fail "port lists must contain only integers"
    exit 2
  }
done

if [[ "$(id -u)" -eq 0 ]]; then
  PRIVILEGED=()
else
  command -v sudo >/dev/null 2>&1 || {
    log fail "root or passwordless sudo is required"
    exit 2
  }
  sudo -n true >/dev/null 2>&1 || {
    log fail "passwordless sudo is required"
    exit 2
  }
  PRIVILEGED=(sudo -n)
fi

for command in systemctl ss wg fail2ban-client; do
  command -v "${command}" >/dev/null 2>&1 || fail "required command is missing: ${command}"
done
SSHD_BIN="$(command -v sshd || true)"
[[ -n "${SSHD_BIN}" ]] || SSHD_BIN=/usr/sbin/sshd
[[ -x "${SSHD_BIN}" ]] || fail "sshd executable is missing"

if (( failures > 0 )); then
  log summary "status=failed failures=${failures}"
  exit 1
fi

effective_sshd="$("${PRIVILEGED[@]}" "${SSHD_BIN}" -T)"
setting() {
  local name="$1"
  awk -v key="${name}" '$1 == key {print $2; exit}' <<< "${effective_sshd}"
}

expect_setting() {
  local name="$1"
  local expected="$2"
  local actual
  actual="$(setting "${name}")"
  if [[ "${actual}" == "${expected}" ]]; then
    ok "sshd ${name}=${actual}"
  else
    fail "sshd ${name}=${actual:-<empty>} expected=${expected}"
  fi
}

expect_setting logingracetime 30
expect_setting maxstartups 20:30:40
expect_setting persourcemaxstartups 10
expect_setting pubkeyauthentication yes
expect_setting passwordauthentication no
expect_setting kbdinteractiveauthentication no
permit_root="$(setting permitrootlogin)"
if [[ "${permit_root}" == "without-password" || "${permit_root}" == "prohibit-password" ]]; then
  ok "sshd permitrootlogin=${permit_root}"
else
  fail "sshd permitrootlogin=${permit_root:-<empty>} expected key-only root"
fi

if systemctl is-active --quiet fail2ban.service; then
  ok "fail2ban service is active"
else
  fail "fail2ban service is not active"
fi
if "${PRIVILEGED[@]}" fail2ban-client status "${FAIL2BAN_JAIL}" >/dev/null 2>&1; then
  ok "fail2ban jail ${FAIL2BAN_JAIL} is active"
else
  fail "fail2ban jail ${FAIL2BAN_JAIL} is not active"
fi

check_fail2ban_value() {
  local key="$1"
  local expected="$2"
  local actual
  actual="$("${PRIVILEGED[@]}" fail2ban-client get "${FAIL2BAN_JAIL}" "${key}" 2>/dev/null || true)"
  if [[ "${actual}" == "${expected}" ]]; then
    ok "fail2ban ${key}=${actual}"
  else
    fail "fail2ban ${key}=${actual:-<empty>} expected=${expected}"
  fi
}

check_fail2ban_value maxretry 5
check_fail2ban_value findtime 600
check_fail2ban_value bantime 3600
ignore_output="$("${PRIVILEGED[@]}" fail2ban-client get "${FAIL2BAN_JAIL}" ignoreip 2>/dev/null || true)"
for expected_network in 127.0.0.0/8 ::1 10.77.0.0/29; do
  if grep -Fq -- "${expected_network}" <<< "${ignore_output}"; then
    ok "fail2ban ignores ${expected_network}"
  else
    fail "fail2ban ignoreip is missing ${expected_network}"
  fi
done

if "${PRIVILEGED[@]}" wg show wg-mvn >/dev/null 2>&1; then
  ok "WireGuard interface wg-mvn is active"
else
  fail "WireGuard interface wg-mvn is not active"
fi

declare -A found_ports=()
while read -r _state _recv_q _send_q local_endpoint _peer_endpoint; do
  port="${local_endpoint##*:}"
  is_port_listed "${port}" || continue
  found_ports["${port}"]=true
  address="${local_endpoint%:*}"
  address="${address#[}"
  address="${address%]}"
  case "${address}" in
    127.0.0.1|::1|"${EXPECTED_WG_IP}")
      ok "listener ${address}:${port} is private"
      ;;
    *)
      fail "sensitive listener ${local_endpoint} is not loopback/WireGuard-only"
      ;;
  esac
done < <(ss -H -lnt)

for port in ${EXPECTED_LISTEN_PORTS}; do
  [[ "${found_ports[${port}]:-}" == "true" ]] || fail "expected private listener is missing: ${port}"
done

if (( failures > 0 )); then
  log summary "status=failed failures=${failures}"
  exit 1
fi
log summary "status=passed failures=0"
