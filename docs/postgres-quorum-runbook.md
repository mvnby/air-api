# PostgreSQL Quorum Runbook

This runbook defines the quorum layer required before PostgreSQL can move from
manual active-passive promotion to Patroni-managed failover.

The etcd layer does not promote PostgreSQL by itself. Installing etcd is safe
while the current primary/standby setup remains active. Do not enable Patroni
against production data until every migration gate in this document passes.

## Topology

| Member | SSH alias | WireGuard IP | etcd role | PostgreSQL role |
| --- | --- | --- | --- | --- |
| API VPS | `mvn-api` | `10.77.0.2` | voting member | primary or replica |
| Reserve VPS | `zakup` | `10.77.0.1` | voting member | primary or replica |
| Web VPS | `mvn` | `10.77.0.3` | voting witness | none initially |

The three etcd members use Raft. Two reachable members are required to elect or
retain a leader. Patroni will later use that leader lease to ensure that only
one PostgreSQL node may accept writes.

Only WireGuard addresses may listen on etcd ports:

- `2379/tcp`: TLS client traffic from Patroni and operators;
- `2380/tcp`: mutual-TLS peer traffic between etcd members.

Do not publish these ports on a public interface. The Compose file uses host
networking so it can bind directly to each node's WireGuard address.

## Tracked Assets

- `deploy/ha/quorum/docker-compose.etcd.yml`: digest-pinned etcd 3.6.11 service;
- `deploy/ha/quorum/etcd.env.example`: per-node non-secret settings;
- `deploy/ha/quorum/mvn-etcd-quorum.service`: boot ordering and lifecycle;
- `scripts/ha/generate_etcd_pki.sh`: private CA and certificate generator;
- `scripts/ha/check_etcd_quorum.sh`: member, leader, Raft lag, and health check.
- `deploy/ha/patroni/`: pinned PostgreSQL/Patroni image, validated config renderer,
  role-agent unit, and isolated rehearsal cluster;
- `scripts/ha/rehearse_patroni_failover.sh`: disposable failover/rejoin drill;
- `scripts/ha/patroni_role_agent.py`: local API/scheduler/bot role reconciler.
- `.github/workflows/patroni-failover-rehearsal.yml`: weekly isolated drill and
  retained diagnostic log.

## PKI

Generate the PKI only on an operator machine with an encrypted disk:

```bash
umask 077
ETCD_PKI_OUTPUT_DIR="$HOME/.mvn/etcd-pki" \
  bash scripts/ha/generate_etcd_pki.sh
```

The output has four distributable bundles:

```text
nodes/mvn-api/{ca.crt,node.crt,node.key}
nodes/zakup/{ca.crt,node.crt,node.key}
nodes/mvn-web/{ca.crt,node.crt,node.key}
operator/{operator.crt,operator.key}
```

Never copy `ca-private/ca.key` to a server. Keep it offline after the three node
certificates are installed. A lost node key can then be replaced without
replacing the cluster CA.

## Installation Gate

Before installation:

1. Back up `/etc/wireguard/wg-mvn.conf` on `mvn-api` and `zakup`.
2. Add `mvn` as `10.77.0.3/32` to both existing peers and configure a full-mesh
   `wg-mvn` interface on `mvn`.
3. Allow UDP `51820` only between the three public server IPs.
4. Verify all six directed WireGuard pings.
5. Confirm public `2379/2380` are closed on every host.

Install one node bundle and the tracked runtime under `/opt/mvn-quorum` on each
host. The `.env` values are:

```text
mvn-api: ETCD_NAME=mvn-api ETCD_WG_IP=10.77.0.2
zakup:   ETCD_NAME=zakup   ETCD_WG_IP=10.77.0.1
mvn:     ETCD_NAME=mvn-web ETCD_WG_IP=10.77.0.3
```

Install the systemd unit as `/etc/systemd/system/mvn-etcd-quorum.service`, then
start all three members within the same operation:

```bash
systemctl daemon-reload
systemctl enable --now mvn-etcd-quorum.service
```

Run the cluster check from any member:

```bash
bash /opt/mvn-quorum/check_etcd_quorum.sh
```

Expected result:

```text
etcd_quorum_status=passed members=3 ... raft_lag=0 ...
```

## Quorum Drill

The pre-Patroni drill is non-destructive to PostgreSQL:

1. Stop one non-leader etcd member.
2. Confirm the remaining two report three configured members, one leader, and
   healthy reachable endpoints.
3. Restart the member and wait until Raft lag returns below 100.
4. Repeat with the current etcd leader and confirm a new leader is elected.
5. Never stop two members together.

Before Patroni adoption, stopping the entire etcd cluster has no effect on the
current PostgreSQL primary. After Patroni adoption, quorum loss deliberately
prevents automatic promotion and may fence the leader depending on the tested
Patroni policy.

## Patroni Migration Gates

Production PostgreSQL may move under Patroni only after all of these are true:

- disposable two-node Patroni failover and rejoin drill passes;
- etcd survives each single-member failure;
- PostgreSQL PITR and both restore workflows are green;
- current physical replication lag is within the release threshold;
- a fresh volume-level rollback copy exists on both database hosts;
- Patroni configuration validation passes on the exact production image;
- watchdog behavior is tested before `watchdog.mode=required` is enabled;
- Cloudflare still observes exactly one `/api/ready=200` origin;
- an operator approves a 2-5 minute write maintenance window.

The initial production policy should use synchronous mode without strict write
blocking. When the synchronous replica is healthy, acknowledged transactions
are present on both database hosts. If the replica is unavailable, the service
may continue writing, but Patroni must refuse a loss-unsafe automatic promotion.
PITR remains the final recovery layer.

## Runtime Role Handoff

Patroni controls only PostgreSQL. The role agent maps the local Patroni role to
two non-secret env files consumed by the app and bot containers:

```text
.ha-app-role.env
.ha-bot-role.env
```

On a replica, it stops the bot, disables scheduler/bootstrap, and keeps
`API_READY_ENABLED=false`. On a stable primary, it waits for the promotion
delay, recreates only the active API slot with scheduler enabled, requires
writable `/api/ready=200`, and then starts the bot. It never runs `compose up`
for `db` and shares the existing `.deploy.lock` with application releases.

This ordering prevents Cloudflare from routing to a promoted database before
the singleton processes have moved, and prevents two Telegram pollers from
running intentionally. PostgreSQL read-only checks remain an independent fence
on the former primary.

Install the agent only during the Patroni migration window:

```bash
install -m 0755 scripts/ha/patroni_role_agent.py \
  /usr/local/sbin/mvn-patroni-role-agent
install -m 0644 deploy/ha/patroni/mvn-patroni-role-agent.service \
  /etc/systemd/system/mvn-patroni-role-agent.service
install -m 0600 deploy/ha/patroni/role-agent.env.example \
  /etc/default/mvn-patroni-role-agent
```

Edit the non-secret host paths/ports in `/etc/default/mvn-patroni-role-agent`,
run `--once`, verify the generated role files, and only then enable the unit.
