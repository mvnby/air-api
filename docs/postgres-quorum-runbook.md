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
- `scripts/ha/rehearse_patroni_failover.sh`: disposable failover/rejoin drill
  that can either build source locally or fail closed around one exact published
  `linux/amd64` digest and prove both running image IDs plus archive behavior;
- `scripts/ha/patroni_role_agent.py` with its
  `patroni_local_identity.py`, `patroni_role_agent_config.py`, and
  `patroni_compose_runtime.py` siblings: local API/scheduler/bot role reconciler
  with strict local DCS leader-lock proof.
- `.github/workflows/patroni-failover-rehearsal.yml`: weekly source-only drill
  (`release_evidence=false`) plus manual exact-digest rehearsal and retained log.
- `.github/workflows/publish-patroni-image.yml`: manual, CI-gated publication of
  the production Patroni image with provenance, SBOM, and immutable digest.
- `deploy/ha/mvn-api/docker-compose.patroni.yml` and
  `deploy/ha/zakup/docker-compose.patroni.yml`: host-specific adoption compose
  files. Normal API deploys must never recreate their `db` service.
- `deploy/ha/proxy/`: the stable internal Nginx hop used only on `zakup`, so
  belzakupki Caddy never needs to follow blue/green container names.
- `docs/infrastructure-security-runbook.md`: tracked SSH/fail2ban policy and
  scheduled private-listener/public-port auditing for all three quorum hosts.

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

Before distribution, inspect `ca.crt` and require both critical extensions:
`Basic Constraints: CA:TRUE` and `Key Usage: Certificate Sign, CRL Sign`.
Validate the exact production Patroni image against every live etcd endpoint
with this CA before opening the PostgreSQL cutover window. `etcdctl` accepting a
certificate is not sufficient because Patroni's Python/OpenSSL client applies
stricter CA validation.

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

## Immutable Patroni Image

Publish only a CI-tested `main` revision. The workflow accepts only an exact
successful `push` CI run for the same SHA, builds a run-scoped candidate,
validates the registry digest, `linux/amd64` runtime, BuildKit provenance and
non-empty SPDX SBOM, creates and verifies a GitHub attestation, then rehearses
that exact digest. Only after all of those checks does it create the SHA tag:

```bash
gh workflow run publish-patroni-image.yml --ref main
```

The SHA tag is only a discoverability alias; the workflow proves that it has
the same top-level digest and refuses to overwrite a conflicting tag. Copy the
resulting `ghcr.io/.../patroni@sha256:...` reference into the protected
`.env` on both database hosts as `PATRONI_IMAGE`. Never use a mutable Patroni
tag in production. Publishing the image does not restart or alter PostgreSQL.

To repeat a release-evidence rehearsal without publishing or changing a tag:

```bash
gh workflow run patroni-failover-rehearsal.yml \
  -f image_digest=sha256:<64-hex-digest>
```

Before any Compose validation, both hosts must also have:

```text
PATRONI_REPLICATION_USERNAME=<existing replication role>
PATRONI_REPLICATION_PASSWORD=<matching password>
PATRONI_IMAGE=ghcr.io/.../patroni@sha256:...
```

The node certificate bundle belongs in `<project>/patroni-pki` with directory
mode `0700`, key mode `0600`, and certificate mode `0644`. The CA private key
must not be present on either server.

Both production Patroni compose files declare the existing PGDATA volumes as
external state:

```text
mvn-api: air-api_postgres_data
zakup:   mvn_reserve_postgres_data
```

This makes `docker compose down -v` unable to delete production PGDATA. Confirm
both volumes with `docker volume inspect` before staging the compose files. A
new database host must create or restore the named external volume explicitly;
Compose must fail closed instead of silently creating an empty database.

## Reserve Proxy Gate

`zakup` shares Caddy with belzakupki. Do not make release jobs rewrite that
Caddyfile. Before the PostgreSQL window:

1. Install `deploy/ha/proxy/nginx.conf` and `upstream.conf` under
   `/opt/mvn-reserve/api-proxy`.
2. Start only `api-proxy` from `docker-compose.patroni.yml`; do not start `db`.
3. Verify `http://127.0.0.1:18080/api/health` reaches the existing fenced app.
4. Back up `/opt/belzakupki/Caddyfile`, replace only the MVN upstream
   `mvn_reserve-app-1:8000` with `mvn_reserve-api-proxy-1:8000`, run
   `caddy validate`, reload Caddy, and smoke-check both MVN and maxikor.fun.
5. Keep `upstream.conf` as runtime state. Normal releases switch it between
   `app-blue:8000` and `app-green:8000`; they never edit the Caddyfile.

Rollback for this gate is the single backed-up Caddyfile plus a validated Caddy
reload. The existing app remains running throughout the gate.

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

Demotion first writes `.ha-runtime-role=fencing`. That durable intermediate
state survives process crashes, Docker inventory failures, and a concurrent
deploy. The agent commits `standby` only while holding `.deploy.lock`, after it
has repeated exact-name fencing, force-recreated the selected app from the
standby env, and proved the final Docker and systemd postconditions. Treat a
persistent `fencing` value as an incomplete demotion; never overwrite it by
hand, because the next agent poll must resume the fence.

The same role transition disables IMAP imports and Cloudflare purge on a
replica. `mvn-postgres-wal-upload.timer` and
`mvn-postgres-basebackup.timer` are stopped on a replica and started only after
the promoted primary API becomes writable. Timer failures are visible in the
agent log but do not hold customer traffic offline.

This ordering prevents Cloudflare from routing to a promoted database before
the singleton processes have moved, and prevents two Telegram pollers from
running intentionally. PostgreSQL read-only checks remain an independent fence
on the former primary.

Install the agent only during the Patroni migration window:

```bash
install -m 0644 scripts/ha/patroni_local_identity.py \
  /usr/local/sbin/patroni_local_identity.py
install -m 0644 scripts/ha/patroni_role_agent_config.py \
  /usr/local/sbin/patroni_role_agent_config.py
install -m 0644 scripts/ha/patroni_compose_runtime.py \
  /usr/local/sbin/patroni_compose_runtime.py
install -m 0755 scripts/ha/patroni_role_agent.py \
  /usr/local/sbin/mvn-patroni-role-agent
install -m 0644 deploy/ha/patroni/mvn-patroni-role-agent.service \
  /etc/systemd/system/mvn-patroni-role-agent.service
install -m 0600 deploy/ha/patroni/role-agent.env.example \
  /etc/default/mvn-patroni-role-agent
```

Edit the non-secret host paths/ports in `/etc/default/mvn-patroni-role-agent`,
run `--once`, verify the generated role files, and only then enable the unit.
During a PITR host transaction, the installer owns the root-only regular file
`/run/mvn-postgres-pitr-maintenance` in mode `0600`; its exact content is the
32-character lowercase hexadecimal transaction id plus one newline. The role
agent continues reconciling primary app/bot traffic while this marker is valid,
but keeps all PITR timers and their services fenced. Unsafe marker metadata or
content causes a full standby fence.

### Communications Worker Phase 2A

Both Patroni API nodes define `communications-worker` from the exact immutable
`BACKEND_IMAGE` used by the API. It uses that node's local PostgreSQL service
and the same role-resolved `.ha-app-role.env`; deploy and verification reject
any image or `APP_ROLE` mismatch. During Phase 2A both delivery gates,
`COMMUNICATIONS_WORKER_ENABLED` and `COMMUNICATIONS_WORKER_ALLOW_ALL_MODE`,
must remain exactly `false`.

The root-owned project marker
`.ha-communications-worker-release-fenced` is a durable fail-closed latch.
While it exists, including as a broken symlink, the role agent keeps the worker
stopped. A release sets the latch before stopping or replacing the worker,
clears it only under the deployment lock immediately before a controlled
start, and latches it again on any failed start or verification. Rollback
restores both the previous marker state and the previous worker running state;
it never starts a worker that was already fenced.

After each node deploy, the verifier proves the canonical Compose file is a
regular non-symlink, API/worker image parity, false delivery gates, the expected
runtime role, a stable active role-agent unit, and an absent release latch. It
then runs `/usr/local/sbin/mvn-patroni-role-agent --once`. A successful no-op
or reconciliation must end with exactly:

```text
patroni_role_agent_once_status=verified role=<primary|standby>
```

Do not enable either delivery gate manually during Phase 2A. Delivery
activation, token ownership, retry/ack canaries, and accumulated-event policy
belong to the separately approved Phase 2B transaction.

## Production Cutover

The following steps require one approved 2-5 minute write window. Do not begin
while a GitHub production release is running.

1. Confirm etcd has three healthy members and no existing MVN Patroni DCS keys.
2. Confirm PITR, both restore drills, physical replication lag, and the latest
   API/Cloudflare report are green.
3. Disable both PITR timers temporarily, stop the role agent if installed, and
   create a deployment maintenance marker on both database hosts.
4. Stop app, scheduler, and bot processes on both hosts; verify no new writes.
5. Re-check zero replication lag, stop both PostgreSQL containers, and create a
   compressed, checksummed PGDATA rollback copy on each host. Verify the
   external volume names are still `air-api_postgres_data` and
   `mvn_reserve_postgres_data` before either Patroni container starts.
6. Start only the current primary `db` with its Patroni compose. Require local
   `/primary=200`, writable SQL, the expected system identifier, and one DCS
   leader before continuing.
7. Start only the reserve `db` with its Patroni compose. Require `/replica=200`,
   streaming state, matching timeline/system identifier, zero replay lag, and
   registration as the synchronous standby.
8. Run the role agent once on both nodes. Require exactly one public
   `/api/ready=200`, one bot, one scheduler, and PITR timers only on the primary.
9. Enable the role-agent units, remove maintenance markers, then run an
   operator-controlled switchover and switchback drill before declaring the
   migration complete.

If any gate before step 8 fails, stop both Patroni containers, restore the old
compose files and PGDATA copies, start the former primary first, then restore
physical replication. Do not delete rollback copies or Patroni DCS state until
the old topology is verified; DCS cleanup is a separate, explicit retry step.

## CI/CD Role Switch

Keep repository variable `API_DB_HA_MODE` unset during preparation and the
database cutover. The existing physical primary/standby release path remains
active while it is unset.

After Patroni, both role agents, the reserve proxy, and the switchover drill are
green, define these environment variables:

| Environment | `API_NODE_HOST` | `API_NODE_USER` | `API_NODE_PROJECT_DIR` |
| --- | --- | --- | --- |
| `production-api` | API VPS address | `root` | `/opt/air-api` |
| `standby-api` | reserve VPS address | `root` | `/opt/mvn-reserve` |

Both environments must retain `SSH_KEY` and `GHCR_PAT`. Then set the repository
variable:

```bash
gh variable set API_DB_HA_MODE --body patroni
```

The next release will:

1. build one immutable backend image from the exact CI-tested SHA;
2. probe both local Patroni APIs and require exactly one primary;
3. run migrations only on that primary while holding the deployment lock;
4. update and smoke-check the fenced replica first;
5. blue-green the current primary through its host-specific proxy;
6. fail the release if the database role changes mid-operation.

The Patroni deploy scripts never start, recreate, or pull `db`. For a full
rollback to the former physical topology, restore PostgreSQL first under the
cutover rollback procedure, then delete `API_DB_HA_MODE`; do not switch the
variable while Patroni is still managing either database node.

## Exact Patroni Image Rolling Transaction

Use `.github/workflows/rollout-patroni-image.yml` only for the reviewed
two-node transition from the exact current Patroni digest to one exact
published target digest. The supported starting DCS generations are deliberately
narrow: `archive_mode=on`, `archive_timeout=300`, and either the compiled legacy
local-copy `archive_command` or the already-promoted immutable helper command.
The controller journals the complete starting DCS document on both nodes,
rejects every other command, and allows no drift outside the reviewed
archive-command transition. It does not authorize an `off -> on` PITR migration
or any other DCS edit.

The approved workflow requires the tested `deploy_sha`, both immutable image
digests, the exact successful `Publish Patroni Image` `publish_run_id` and
`publish_run_attempt`, a new
rollout transaction id, the exact transaction id already stored in
`/run/mvn-postgres-pitr-maintenance`, `apply=true`, and `resume=false`. Before
opening SSH, the workflow proves the publish run's workflow identity, latest
attempt, main SHA and successful conclusion; downloads its exact evidence
artifact; binds the raw manifest and rehearsal log to the target digest;
re-resolves the live `patroni:<deploy_sha>` tag; and independently rechecks
registry provenance, SPDX SBOM and the GitHub SLSA attestation. A standalone
failover rehearsal is never release evidence.

The existing PITR marker is retained throughout; its exact id is journal-bound,
and all PITR timers and services remain inactive. A retry must reuse every
original input, including both publish identifiers, with `resume=true`. Never create a
new transaction while either host has the old transaction marker or journal.

The controller performs this fixed sequence:

1. Prove source-bound Compose, helper, etcd, role-agent, SSH, image, DCS,
   archive, quorum, lineage, and runtime-ownership contracts on both hosts.
2. Pull and attest the exact target image on both hosts without rebuilding it.
3. Recreate the current standby only, prove it remained a standby, and record
   the completed generation.
4. Perform one exact Patroni switchover, rediscover the new timeline, then
   recreate the former primary as the standby. Image rollback is forbidden
   after this boundary.
5. Only after both target runtimes and API/bot/scheduler ownership are proved,
   change the single DCS path `postgresql.parameters.archive_command`.
6. Force a WAL switch, prove the exact segment and archiver counters, re-prove
   quorum/topology/runtime ownership, then finalize the final standby first and
   the final primary last.

Root-only canonical journals live under
`/var/lib/mvn-patroni-rollout/transactions/`; the separate per-project marker
is `.patroni-cutover-in-progress`. Normal API deployments and migrations share
the same safely opened `.deploy.lock` and must refuse to start while this
marker exists. Resume reconciles interrupted node updates, switchover records,
DCS compensation, abort, and partial finalization from the journals before
requiring a fully healthy topology.

Both local and remote Compose contract renders must use the canonical project
directory (`/opt/air-api` for `mvn-api`, `/opt/mvn-reserve` for `zakup`). Relative
bind mounts are contract data, so rendering them relative to a CI checkout
produces a different and invalid contract even when the tracked Compose bytes
are identical.

Transaction `1053e46eb933ebaaffed042ac1b73170` is a reviewed preflight-only incident:
its journals contain only the baseline-primary record and no image, PostgreSQL,
switchover, or DCS mutation. Recover it only with the manual
`Recover Patroni Preflight Incident` workflow from the exact current tested
`main` SHA. The workflow accepts the exact before/after journal hashes, proves
the old runtime image, corrected Compose contracts, legacy DCS generation,
topology, disabled PITR units, and both maintenance markers under the rollout
and deploy locks. It then atomically appends only `abort`, writes immutable
root-only receipts, re-proves both nodes, and removes only the two cutover
markers. It never removes `/run/mvn-postgres-pitr-maintenance`; never edits
`.env`, Compose, DCS, or images; and is safe to retry after either journal or
marker boundary. Never continue that incident with the normal rollout workflow;
start the next rollout with a new transaction id and new publish evidence.

Before the switchover boundary, failure restores the old standby image and
legacy DCS generation before removing either marker. After the boundary, the
only permitted direction is roll-forward. If the new archive helper proof
fails, the controller restores the exact journaled legacy DCS snapshot and
keeps both hosts fenced for a same-transaction retry. Do not remove markers or
edit journals manually. Enabling remote PITR upload, changing timers, or
removing the PITR maintenance marker is a separate later transaction after
this image rollout is fully finalized.

## Production Monitoring

After `API_DB_HA_MODE=patroni`, the existing scheduled workflows become
role-aware instead of treating the API VPS as a permanent primary:

- `PostgreSQL Replication Check` runs every ten minutes and invokes
  `scripts/ha/check_patroni_production.py`;
- `PostgreSQL PITR Check` probes both Patroni REST APIs and executes the local
  archive/timer/R2 freshness check on whichever node is currently primary;
- both workflows retain the existing Telegram failure action and diagnostic
  artifacts.

Scheduled HA checks recognize an official maintenance window only after
`scripts/ha/check_patroni_maintenance.py` proves the marker independently on
both hosts. Both markers must be root-owned regular `0600` files with one link,
contain the same 32-character transaction id, be no older than two hours, and
remain stable while read. Both role agents must still be active and every PITR
timer must be inactive. A valid window is logged and reported as maintenance,
not as a passing infrastructure check; the disruptive check itself is skipped.
Missing markers on both nodes mean normal operation. A partial, mismatched,
unsafe, future-dated, or stale marker fails closed and still sends the normal
alert.

This gate is applied to replication, active/passive invariants, HA readiness,
VPS health, HA status rollups, and the strict PITR check. Scheduled restore
drills may also skip a proven maintenance window. Manually dispatched restore
drills never skip it silently: they fail with an explicit maintenance error so
an operator cannot mistake a non-run drill for a recovery proof.

The production checker requires all of these invariants at the same time:

1. exactly one Patroni primary and one running replica;
2. both DCS views identify the same leader and synchronous standby;
3. matching PostgreSQL system identifiers, synchronous streaming, and replay
   lag within `POSTGRES_REPLICATION_MAX_LAG_BYTES`;
4. healthy three-member etcd quorum;
5. active role agents, one bot, one traffic-enabled API, and the standby API
   fenced with HTTP 503;
6. PITR timers active only on the current primary.

Manual operator check from a machine with both SSH aliases:

```bash
python3 scripts/ha/check_patroni_production.py
```

The first required scheduled runs must pass after the switchover and switchback
drill. Keep `watchdog.mode=off` until a real fencing device is installed and a
separate destructive-node rehearsal proves it; etcd quorum alone is not a
substitute for watchdog fencing.
