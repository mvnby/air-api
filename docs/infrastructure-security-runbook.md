# Infrastructure Security Runbook

This runbook covers the three hosts in the MVN reliability topology:

| Host | WireGuard IP | Public services | Private services |
| --- | --- | --- | --- |
| `mvn-api` | `10.77.0.2` | SSH, HTTPS | PostgreSQL, etcd, Patroni, API slots |
| `zakup` | `10.77.0.1` | SSH, shared Caddy HTTPS | PostgreSQL, etcd, Patroni, MVN proxy/app slots |
| `mvn` | `10.77.0.3` | SSH, web HTTPS | etcd witness |

Do not enable or rewrite UFW on `mvn-api` or `zakup` as an incidental
hardening step. Docker networking and the existing WireGuard mesh must be
modeled first. The enforced boundary is: database, quorum, role API, and
internal application ports bind only to loopback or `10.77.0.0/29`; public
reachability is checked independently from a GitHub runner.

## Tracked Policy

- `deploy/ha/security/00-mvn-cicd-reliability.conf`: effective SSH policy;
- `deploy/ha/security/mvn-sshd.local`: fail2ban SSH jail policy;
- `scripts/ha/check_host_security.sh`: host-local effective-state audit;
- `.github/workflows/check-infrastructure-security.yml`: three-host and public
  listener audit every six hours.

The SSH policy allows root only with a key because the current release path is
root-based. Password and keyboard-interactive login stay disabled. CI
connection bursts are bounded by `MaxStartups 20:30:40` and
`PerSourceMaxStartups 10`; fail2ban remains the abuse-control layer.

## Safe Apply

Keep one working SSH session open throughout the operation. Apply one host at a
time and do not continue until a second independent SSH session succeeds.

```bash
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
cp -a /etc/ssh/sshd_config.d/00-mvn-cicd-reliability.conf \
  "/etc/ssh/sshd_config.d/00-mvn-cicd-reliability.conf.bak-${stamp}" 2>/dev/null || true
cp -a /etc/fail2ban/jail.d/mvn-sshd.local \
  "/etc/fail2ban/jail.d/mvn-sshd.local.bak-${stamp}" 2>/dev/null || true
```

Stage the tracked files with mode `0644`, then validate before reload:

```bash
sshd -t
fail2ban-client -t
systemctl reload ssh
systemctl reload fail2ban
```

Do not restart SSH. Open a new session and run the local checker with the host's
WireGuard address and required listeners:

```bash
# mvn-api
EXPECTED_WG_IP=10.77.0.2 \
EXPECTED_LISTEN_PORTS="2379 2380 5432 8008" \
bash scripts/ha/check_host_security.sh

# zakup
EXPECTED_WG_IP=10.77.0.1 \
EXPECTED_LISTEN_PORTS="2379 2380 5432 8008" \
bash scripts/ha/check_host_security.sh

# mvn web/witness
EXPECTED_WG_IP=10.77.0.3 \
EXPECTED_LISTEN_PORTS="2379 2380" \
bash scripts/ha/check_host_security.sh
```

Before Patroni adoption, omit `8008` on the two database hosts. The scheduled
workflow handles this automatically from `API_DB_HA_MODE`.

## Required Invariants

The checker fails unless all of these remain true:

1. password and keyboard-interactive SSH authentication are disabled;
2. root login is key-only and public-key authentication is enabled;
3. SSH connection limits match the tracked CI-safe values;
4. fail2ban and its `sshd` jail are active with the tracked retry/window/ban
   limits;
5. loopback and the WireGuard subnet are excluded from fail2ban bans;
6. `wg-mvn` is active;
7. sensitive listeners use only loopback or the node's WireGuard address;
8. the same sensitive ports are closed on all public server addresses.

The external workflow uploads its audit log and sends the existing HA Telegram
alert on failure. It is included in `scripts/ha/report_ha_status.py`, so a stale
or failed security check makes the aggregate reliability report require
attention.

The web deployment continues to use `SSH_USER_WEB` (normally `deploy`). The
security audit uses repository variable `INFRA_SECURITY_WEB_USER`, defaulting
to `root`, because reading fail2ban's control socket requires privilege. Keep
these identities separate; do not grant the web deploy user broad sudo merely
to satisfy monitoring.

## Rollback

If `sshd -t` or `fail2ban-client -t` fails, do not reload either service.
Restore the timestamped file and validate again. If a reload succeeded but a
new SSH session fails, use the still-open operator session or provider console
to restore the backup, then reload SSH. Never close the last working session
until an independent key-only login and `check_host_security.sh` both pass.

Changing firewall policy, rotating SSH host keys, moving away from root-based
deploys, or enabling Patroni watchdog fencing are separate changes with their
own rollback plans. They must not be bundled into this config reload.
