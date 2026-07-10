# API HA Runbook

This document remains the rollback/reference runbook for the physical
active-passive topology. Once repository variable `API_DB_HA_MODE=patroni`, use
`docs/postgres-quorum-runbook.md` for database role changes and do not run the
manual physical promotion helpers below against a Patroni-managed node.

This runbook describes the current active-passive API setup for `api.mvn.by`.
The system intentionally has one writable PostgreSQL primary and one warm
standby. Do not make both origins public-writable.

Last verified state: 2026-07-03.

## Current Hosts

| Host | SSH alias | Current role | API path | API port |
| --- | --- | --- | --- | --- |
| Original API VPS | `mvn-api` | Active primary | `/opt/air-api` | nginx `127.0.0.1:18080` -> slot `18001/18002` |
| Belarus reserve VPS | `zakup` | Warm standby | `/opt/mvn-reserve` | `127.0.0.1:18000` |
| Web VPS | `mvn` | Storefront only | n/a | n/a |

Current data direction:

```text
mvn-api PostgreSQL primary 10.77.0.2:5432
  -> zakup PostgreSQL physical standby 10.77.0.1:5432, slot zakup_standby

new runtime media writes
  -> Cloudflare R2/CDN at https://cdn.mvn.by/...

legacy local /media fallback
  -> zakup /opt/mvn-reserve/media via mvn-media-sync.timer every 5 minutes
```

Runtime split:

| Runtime | `mvn-api` primary | `zakup` standby |
| --- | --- | --- |
| Public readiness | `/api/ready` returns 200 | `/api/ready` returns 503 |
| FastAPI app | running | running for health only |
| PostgreSQL | writable primary | read-only physical replica |
| Scheduler | enabled in `app` | disabled |
| Telegram bot | enabled only in `bot` | stopped/disabled |
| Google Drive backups | enabled on primary scheduler | disabled |
| New media writes | R2/CDN | disabled while standby |
| Legacy local media | source of sync | pulled from primary |

## Repo-Tracked HA Files

The active-passive setup is tracked in the repo so deploys do not depend on
unreviewed host-local compose edits:

| Purpose | File |
| --- | --- |
| `mvn-api` as primary | `deploy/ha/mvn-api/docker-compose.primary.yml` |
| `mvn-api` as rebuilt standby | `deploy/ha/mvn-api/docker-compose.standby.yml` |
| `zakup` as primary after promotion | `deploy/ha/zakup/docker-compose.primary.yml` |
| `zakup` as standby | `deploy/ha/zakup/docker-compose.standby.yml` |
| Active-passive invariant check | `scripts/ha/check_active_passive.sh` |
| Zero-downtime primary API deploy | `scripts/deploy_backend_blue_green.sh` |
| Local standby promotion helper | `scripts/ha/promote_local_standby.sh` |
| GitHub Actions primary switch helper | `scripts/ha/switch_github_api_primary.py` |
| Disposable DB restore drill | `scripts/ha/restore_drill_latest_db.sh` |
| PostgreSQL PITR WAL/basebackup upload | `scripts/ha/upload_postgres_pitr_to_s3.py`, `scripts/ha/upload_postgres_pitr_wal.sh`, `scripts/ha/create_postgres_pitr_basebackup.sh` |
| PostgreSQL PITR restore helpers | `scripts/ha/restore_postgres_pitr_from_s3.py`, `scripts/ha/restore_postgres_pitr_drill.sh`, `.github/workflows/postgres-pitr-restore-drill.yml` |
| PostgreSQL PITR env/bootstrap | `scripts/ha/configure_postgres_pitr_env.py`, `scripts/ha/bootstrap_postgres_pitr.sh` |
| PostgreSQL PITR primary prerequisite apply helper | `scripts/ha/apply_postgres_pitr_primary_prerequisites.py` |
| PostgreSQL PITR monitoring | `scripts/ha/check_postgres_pitr_status.sh`, `scripts/ha/check_postgres_pitr_remote.py`, `.github/workflows/check-postgres-pitr.yml` |
| PostgreSQL PITR systemd units | `deploy/ha/systemd/mvn-postgres-wal-upload.*`, `deploy/ha/systemd/mvn-postgres-basebackup.*` |
| Cloudflare LB primary switch helper | `scripts/ha/switch_cloudflare_lb_primary.py` |
| External strict-mode prerequisite check | `scripts/ha/check_ha_external_prerequisites.py` |
| Operator HA status report | `scripts/ha/report_ha_status.py`, `.github/workflows/report-ha-status.yml` |
| Strict-mode activation helper | `scripts/ha/enable_ha_strict_mode.py` |
| Cloudflare LB GitHub prerequisite apply helper | `scripts/ha/apply_cloudflare_lb_github_prerequisites.py` |
| Status helpers | `scripts/ha/mvn-primary-status.sh`, `scripts/ha/mvn-standby-status.sh` |
| Media sync helper/timer | `scripts/ha/media_sync_pull.sh`, `deploy/ha/systemd/mvn-media-sync.*` |
| PostgreSQL quorum preparation | `docs/postgres-quorum-runbook.md`, `deploy/ha/quorum/`, `deploy/ha/patroni/`, `scripts/ha/generate_etcd_pki.sh`, `scripts/ha/check_etcd_quorum.sh`, `scripts/ha/patroni_role_agent.py` |

## Daily Status Checks

Primary:

```bash
ssh mvn-api /usr/local/sbin/mvn-primary-status
```

Standby:

```bash
ssh zakup /usr/local/sbin/mvn-standby-status
```

Public and direct readiness:

```bash
curl -fsS https://api.mvn.by/api/ready
curl -k --resolve api.mvn.by:443:185.250.45.54 https://api.mvn.by/api/ready
curl -k --resolve api.mvn.by:443:193.47.42.213 https://api.mvn.by/api/ready
```

Expected:

- public readiness: 200 from `mvn-api`;
- direct `mvn-api`: 200;
- direct `zakup`: 503.

Repo check:

```bash
bash scripts/ha/check_active_passive.sh
```

Media storage config check:

```bash
ssh mvn-api 'cd /opt/air-api && app_service=app; if test -f .active-api-slot; then app_service="app-$(cat .active-api-slot)"; fi; docker compose -f docker-compose.prod.yml --profile bluegreen exec -T "$app_service" python3 scripts/check_media_storage_config.py --require-object-storage --expected-public-base-url https://cdn.mvn.by'
```

GitHub health check:

```bash
gh workflow run check-api-vps-health.yml --repo mvnby/air-api --ref main -f mode=ssh
```

Whole-system HA readiness audit:

```bash
gh workflow run check-api-ha-readiness.yml --repo mvnby/air-api --ref main
```

The audit fails on core readiness, replication, and media CDN problems. Until
Cloudflare read-only credentials and PostgreSQL PITR are fully enabled, it
reports those two items as soft blockers. Run with `strict=true` only after
`CLOUDFLARE_LB_CONFIG_REQUIRED=true` and `POSTGRES_PITR_REQUIRED=true` are
intended to be enforced.

External strict-mode prerequisite check:

```bash
python3 scripts/ha/check_ha_external_prerequisites.py --repo mvnby/air-api
python3 scripts/ha/check_ha_external_prerequisites.py --repo mvnby/air-api --require-strict
```

This check uses `gh` metadata only. It lists missing GitHub variables/secrets
without printing secret values. It cannot read host-local private PITR R2
credentials; after those are installed, verify them on the primary with
`ssh mvn-api '/usr/local/sbin/mvn-postgres-pitr-bootstrap verify'`.

Operator rollup report:

```bash
python3 scripts/ha/report_ha_status.py --repo mvnby/air-api
python3 scripts/ha/report_ha_status.py --repo mvnby/air-api --require-strict
```

The default report checks recent GitHub deploy/monitor runs, including its own
scheduled workflow, lists external strict-mode blockers as attention items, and
runs the direct-origin active-passive invariant. Use `--require-strict` before
enabling strict mode; in that mode missing Cloudflare/PITR prerequisites become
hard failures. Treat `[ha-status][next-step]` lines as the immediate operator
checklist; they are derived from the current blockers and failures without
printing secret values.

After creating the Cloudflare LB read-only token and finding the zone/account
ids, put them in local `.env` as:

```bash
CLOUDFLARE_API_TOKEN_LB_AUDIT=<read-only Cloudflare token>
CLOUDFLARE_ZONE_ID=<mvn.by zone id>
CLOUDFLARE_ACCOUNT_ID=<Cloudflare account id>
```

Then apply them to GitHub without printing secret values:

```bash
python3 scripts/ha/apply_cloudflare_lb_github_prerequisites.py --repo mvnby/air-api --env-file .env
```

The helper also accepts `CLOUDFLARE_LB_READ_TOKEN` for the local input token,
but always stores the GitHub Actions secret under the canonical
`CLOUDFLARE_LB_READ_TOKEN` name.

After the required Cloudflare LB workflow passes and you want scheduled checks
to fail on drift, repeat with:

```bash
python3 scripts/ha/apply_cloudflare_lb_github_prerequisites.py --repo mvnby/air-api --env-file .env --mark-required
```

After Cloudflare LB credentials are in GitHub and PostgreSQL PITR has passed
`mvn-postgres-pitr-bootstrap verify`, use the strict-mode activation helper
instead of setting strict variables by hand:

```bash
python3 scripts/ha/enable_ha_strict_mode.py --repo mvnby/air-api --dry-run
python3 scripts/ha/enable_ha_strict_mode.py --repo mvnby/air-api
```

The helper waits for the required Cloudflare LB config audit, PITR status
check, PITR restore drill, and strict HA readiness audit. It sets
`CLOUDFLARE_LB_CONFIG_REQUIRED=true`, `POSTGRES_PITR_REQUIRED=true`, and
`API_HA_READINESS_STRICT=true` only after those proof workflows pass, then runs
the final `report_ha_status.py --require-strict` rollup so the same command
proves GitHub workflows, external prerequisites, and the live active/passive
invariant after strict mode is enabled.

Scheduled monitors:

| Workflow | Schedule | Purpose |
| --- | --- | --- |
| `report-ha-status.yml` | every 2 hours | operator rollup over deploys, monitors, external prerequisites, and direct active/passive state |
| `check-api-vps-health.yml` | every 6 hours | primary host, containers, DB, backups, media storage config |
| `check-api-ha-readiness.yml` | every 6 hours | whole-system HA readiness rollup; direct-origin core checks fail, Cloudflare/PITR are soft blockers until strict |
| `check-api-ha-invariants.yml` | every 30 minutes | direct primary ready and standby fenced; public Cloudflare routing is covered by the LB monitor/config checks |
| `check-cloudflare-lb-config.yml` | every 6 hours | Cloudflare LB pool order, fallback, host header, and monitor config |
| `api-restore-drill.yml` | daily after the 03:00 UTC backup | disposable DB restore drill |
| `check-postgres-pitr.yml` | every 6 hours | PITR archive/timer/backlog and remote R2 freshness |
| `postgres-pitr-restore-drill.yml` | daily when `POSTGRES_PITR_REQUIRED=true` | disposable physical restore from PITR basebackup + WAL |
| `check-media-cdn.yml` | every 6 hours | public product images and DB-backed object-storage media use `cdn.mvn.by`; sampled CDN objects are cacheable |

Owner-visible alerting:

All HA monitor workflows call `.github/actions/notify-ha-failure` on failure
after the log artifact upload step. Without the secrets below, the notifier
prints a skip message and does not fail the workflow:

```bash
gh secret set HA_ALERT_TELEGRAM_BOT_TOKEN --repo mvnby/air-api
gh secret set HA_ALERT_TELEGRAM_CHAT_ID --repo mvnby/air-api
# Optional, only for Telegram forum topics:
gh secret set HA_ALERT_TELEGRAM_THREAD_ID --repo mvnby/air-api
```

The HA status report treats all three names as alerting prerequisites: bot
token and chat id are functionally required for alerts, while thread id only
routes alerts into a Telegram forum topic.

Use a dedicated Telegram bot or a tightly scoped internal alert chat. Do not
reuse the customer-facing bot token for infrastructure alerts.

## PostgreSQL PITR

Streaming replication protects us from a dead primary host. PITR protects us
from operator mistakes, corrupted writes, or needing to restore to a timestamp
before bad data was committed.

The current PITR design uses native PostgreSQL archiving:

```text
primary PostgreSQL archive_command
  -> /opt/air-api/postgres-wal-archive
  -> mvn-postgres-wal-upload.timer
  -> private Cloudflare R2/S3 bucket

mvn-postgres-basebackup.timer
  -> pg_basebackup -Ft -z -X stream
  -> same private Cloudflare R2/S3 bucket
```

Important rules:

- Use a **private** bucket or private prefix for database backups. Do not reuse
  a public media bucket exposed through `cdn.mvn.by`.
- `archive_timeout=300s` bounds low-traffic WAL upload lag to about five
  minutes. The streaming standby still normally has lower failover lag.
- Only primary compose files can enable archiving, and only when
  `POSTGRES_PITR_ARCHIVE_MODE=on` is set. Standby compose keeps archiving
  disabled until it is promoted and restarted with a primary compose file.

Required `.env` values on the current primary before the first upload test:

```text
POSTGRES_PITR_CLUSTER=mvn-api
POSTGRES_PITR_S3_BUCKET=<private-r2-bucket>
POSTGRES_PITR_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
POSTGRES_PITR_S3_REGION=auto
POSTGRES_PITR_S3_ACCESS_KEY_ID=<private-r2-token-access-key>
POSTGRES_PITR_S3_SECRET_ACCESS_KEY=<private-r2-token-secret>
POSTGRES_PITR_S3_KEY_PREFIX=postgres/pitr
```

Create these credentials from Cloudflare R2, not from the regular Cloudflare
API Tokens page. In Cloudflare dashboard open **R2 object storage**, create a
private bucket for database PITR only, then under R2 API tokens create a token
with **Object Read & Write** scoped to that specific private bucket. Record the
shown **Access Key ID** and **Secret Access Key** immediately; Cloudflare shows
the secret only once. Use the S3 API endpoint
`https://<account-id>.r2.cloudflarestorage.com`.

Do not use the public media bucket or a public `r2.dev`/CDN endpoint for PITR.
The helper refuses that configuration because database WAL/basebackups must not
share the public media surface.

If `zakup` is promoted, change `POSTGRES_PITR_CLUSTER=zakup` on that host before
enabling its PITR timers. The prefix can stay the same; cluster name separates
the timelines.

`POSTGRES_PITR_ARCHIVE_MODE` intentionally defaults to `off` in compose. Set it
to `on` only after the private bucket/token are configured and the upload helper
has passed a dry run. This prevents WAL files from accumulating locally before
remote archive upload is ready.

Enable on the current primary after the private bucket/token exist:

```bash
# From local repo checkout, copy/install repo-tracked PITR helpers as root on
# the primary. The installer also creates postgres-wal-archive and chowns it to
# the postgres container UID. No git checkout is required on production.
tar -czf - \
  scripts/ha/upload_postgres_pitr_to_s3.py \
  scripts/ha/upload_postgres_pitr_wal.sh \
  scripts/ha/create_postgres_pitr_basebackup.sh \
  scripts/ha/configure_postgres_pitr_env.py \
  scripts/ha/bootstrap_postgres_pitr.sh \
  scripts/ha/restore_postgres_pitr_from_s3.py \
  scripts/ha/restore_postgres_pitr_drill.sh \
  scripts/ha/check_postgres_pitr_status.sh \
  scripts/ha/check_postgres_pitr_remote.py \
  scripts/ha/install_postgres_pitr_units.sh \
  deploy/ha/systemd/mvn-postgres-wal-upload.service \
  deploy/ha/systemd/mvn-postgres-wal-upload.timer \
  deploy/ha/systemd/mvn-postgres-basebackup.service \
  deploy/ha/systemd/mvn-postgres-basebackup.timer \
| ssh mvn-api 'tmp="$(mktemp -d)" && tar -xzf - -C "$tmp" && cd "$tmp" && PROJECT_DIR=/opt/air-api COMPOSE_FILE=docker-compose.prod.yml bash scripts/ha/install_postgres_pitr_units.sh && rm -rf "$tmp"'

# Copy deploy/ha/mvn-api/docker-compose.primary.yml through CI.
gh workflow run deploy.yml --repo mvnby/air-api --ref main -f deploy_frontend=false

# Put the private R2 credentials in local `.env` using the names above. The
# helper loads only `POSTGRES_PITR_*` keys from that file, uploads a temporary
# root-only env file to the primary, removes it after the remote phase, and
# never prints access keys.

# First verify the local input shape without touching the primary.
python3 scripts/ha/apply_postgres_pitr_primary_prerequisites.py --env-file .env --dry-run --no-prompt

# Then upload the temporary env file and run the remote preflight. This does not
# write the production .env, upload a basebackup, or recreate the database.
python3 scripts/ha/apply_postgres_pitr_primary_prerequisites.py --env-file .env --phase preflight --no-prompt

# Finally validate credentials, write PITR env with archive mode still off,
# upload a physical basebackup, and stage archive_mode=on for the next DB
# recreate. This still does not recreate the database.
python3 scripts/ha/apply_postgres_pitr_primary_prerequisites.py --env-file .env --phase bootstrap-before-maintenance --no-prompt

# In a short maintenance window, recreate db so archive_mode=on and the
# /postgres-wal-archive mount become active. The helper also resets historical
# archiver counters, forces one WAL switch, and proves one WAL upload before
# timers are enabled.
ssh mvn-api 'CONFIRM_RECREATE_DB=true /usr/local/sbin/mvn-postgres-pitr-bootstrap activate-archive'

# Then enable recurring PITR.
ssh mvn-api '/usr/local/sbin/mvn-postgres-pitr-bootstrap enable-timers'

# Finally make the scheduled GitHub PITR check strict, but only after
# `mvn-postgres-pitr-bootstrap verify` and one physical restore drill have both
# passed with archived WAL present.
gh variable set POSTGRES_PITR_REQUIRED --repo mvnby/air-api --body true
```

Quick PITR status:

```bash
ssh mvn-api 'PROJECT_DIR=/opt/air-api COMPOSE_FILE=docker-compose.prod.yml PITR_REQUIRED=true /usr/local/sbin/mvn-postgres-pitr-status'
ssh mvn-api '/usr/local/sbin/mvn-postgres-pitr-bootstrap verify'
ssh mvn-api 'cd /opt/air-api && docker compose -f docker-compose.prod.yml exec -T db sh -lc '\''psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -c "select archived_count,last_archived_wal,last_archived_time,failed_count,last_failed_wal,last_failed_time from pg_stat_archiver;"'\'''
ssh mvn-api 'systemctl list-timers --all | grep mvn-postgres'
```

Manual GitHub monitor run:

```bash
gh workflow run check-postgres-pitr.yml --repo mvnby/air-api --ref main -f required=true
```

Streaming replication monitor:

```bash
bash scripts/ha/check_postgres_replication.sh
gh workflow run check-postgres-replication.yml --repo mvnby/air-api --ref main
```

The replication check is read-only. It verifies that the primary is writable,
the physical slot is active, `pg_stat_replication` reports a streaming standby
under the replay-lag threshold, and the standby database is in recovery with an
active WAL receiver. It intentionally does not print `primary_conninfo` or any
replication password.

Physical PITR restore drill after the first private basebackup and WAL upload:

```bash
ssh mvn-api 'PROJECT_DIR=/opt/air-api COMPOSE_FILE=docker-compose.prod.yml /usr/local/sbin/mvn-postgres-pitr-restore-drill'
```

The drill:

- selects the latest private PITR basebackup unless `BACKUP_ID` is provided;
- downloads and verifies basebackup files and archived WAL into a temporary
  host directory;
- starts a disposable PostgreSQL container against that restored data
  directory;
- checks that public tables and critical MVN tables are queryable;
- removes the temporary container and files by default;
- never mounts or modifies the production or standby PostgreSQL volumes.

Optional point-in-time target:

```bash
ssh mvn-api 'PROJECT_DIR=/opt/air-api COMPOSE_FILE=docker-compose.prod.yml TARGET_TIME=2026-07-02T18:30:00Z /usr/local/sbin/mvn-postgres-pitr-restore-drill'
```

With `TARGET_TIME`, the drill expects PostgreSQL recovery to pause at the target
time. Use this for periodic manual PITR proof after the scheduled latest-backup
drill is green.

Manual GitHub restore-drill run:

```bash
gh workflow run postgres-pitr-restore-drill.yml --repo mvnby/air-api --ref main -f required=true
```

The scheduled workflow skips itself while `POSTGRES_PITR_REQUIRED=false`.
Do not set `POSTGRES_PITR_REQUIRED=true` until both the strict freshness check
and a physical restore drill pass. After that, leave it true so the daily drill
keeps proving that basebackups plus archived WAL can actually be restored.

## GitHub Actions Routing

Current production GitHub secret/variables must match the active primary:

```text
SSH_HOST_API=185.250.45.54
API_PRIMARY_ORIGIN=185.250.45.54
API_STANDBY_ORIGIN=193.47.42.213
API_PROJECT_DIR=/opt/air-api
API_COMPOSE_FILE=docker-compose.prod.yml
API_COMPOSE_SOURCE_FILE=deploy/ha/mvn-api/docker-compose.primary.yml
API_COPY_COMPOSE=true
API_DEPLOY_STRATEGY=blue_green
API_BASE_URL=http://localhost:18080
API_READY_URL=http://localhost:18080/api/ready
API_LOCAL_HEALTH_URL=http://127.0.0.1:18080/api/health
API_TUNNEL_REMOTE_PORT=18080
API_DEPLOY_SERVICES=app bot
API_SMOKE_COMPOSE_SERVICE_CHECKS=app bot db
API_COMPOSE_SERVICE_CHECKS=app bot db
API_BOT_EXPECT_ENABLED=true
API_STANDBY_HOST=193.47.42.213
API_STANDBY_PROJECT_DIR=/opt/mvn-reserve
API_STANDBY_COMPOSE_FILE=docker-compose.reserve.yml
API_STANDBY_COPY_COMPOSE=true
API_STANDBY_COMPOSE_SOURCE_FILE=deploy/ha/zakup/docker-compose.standby.yml
API_STANDBY_HEALTH_URL=http://localhost:18000/api/health
```

Use the helper to switch these GitHub secret/variables after a real promotion
or planned failback. It prints a dry-run plan by default:

```bash
# Normal routing: mvn-api primary, zakup standby.
python3 scripts/ha/switch_github_api_primary.py --repo mvnby/air-api --primary mvn-api
python3 scripts/ha/switch_github_api_primary.py --repo mvnby/air-api --primary mvn-api --confirm

# After zakup has actually been promoted.
python3 scripts/ha/switch_github_api_primary.py --repo mvnby/air-api --primary zakup
python3 scripts/ha/switch_github_api_primary.py --repo mvnby/air-api --primary zakup --confirm
```

The helper updates the `SSH_HOST_API` GitHub secret plus the repo variables
used by deploy, smoke checks, replication checks, standby image deploy, and
Cloudflare origin audits. Run it only after the database role has been changed;
it does not promote PostgreSQL and does not switch Cloudflare traffic.

If an emergency requires manual host-local compose edits, set
`API_COPY_COMPOSE=false` and/or `API_STANDBY_COPY_COMPOSE=false` temporarily.
Switch back to the repo-tracked files after the emergency is resolved.

Manual deploy verification:

```bash
gh workflow run deploy.yml --repo mvnby/air-api --ref main -f deploy_frontend=false
```

The command is accepted only for `main` commits that already have a successful
`CI (Test & Lint)` run. Normal releases start automatically from that successful
CI run. The workflow publishes `backend:<commit_sha>` for traceability, resolves
the build result to `backend@sha256:<digest>`, and deploys that digest to both
hosts. Primary and standby therefore receive the exact artifact built from the
source revision that passed CI; `backend:latest` is not part of production
releases.

Expected deploy behavior:

- primary `mvn-api`: pull only application images, run migrations/defaults in a
  one-off `--no-deps` container, then recreate `app` and `bot` with `--no-deps`;
- standby `zakup`: pull and recreate only `app` with `--no-deps`, then stop
  `bot`; the same deployment lock and guarded code rollback apply there;
- PostgreSQL is never pulled or recreated by an application release. Its image
  is digest-pinned and changes only in a separate database maintenance window;
- after standby deploy: run the active-passive invariant check with public
  Cloudflare readiness skipped, proving the direct primary origin is ready and
  writable while the direct standby origin remains fenced;
- both API hosts: retain the three newest backend images plus every image used
  by a container, then remove only older backend images and dangling images
  older than seven days;
- frontend deploy is skipped unless explicitly requested.

If primary activation or smoke checks fail, the workflow runs a guarded
code-only rollback to `.previous-backend-image`. The guard verifies that the
failed candidate was actually persisted before changing anything. Rollback does
not downgrade Alembic, so every production migration must follow the
expand/contract compatibility policy.

Manual disk pressure check:

```bash
ssh mvn-api 'df -h / && docker system df'
ssh zakup 'df -h / && docker system df'
```

Manual scoped image cleanup, safe for databases, media volumes, and the last
three backend releases:

```bash
cat scripts/prune_unused_docker_images.sh | ssh mvn-api \
  'KEEP_BACKEND_IMAGES=3 bash -s'
cat scripts/prune_unused_docker_images.sh | ssh zakup \
  'KEEP_BACKEND_IMAGES=3 bash -s'
```

Manual zero-downtime code rollback on the current primary:

```bash
scp scripts/deploy_backend_blue_green.sh scripts/rollback_backend.sh mvn-api:/tmp/
ssh mvn-api 'chmod +x /tmp/deploy_backend_blue_green.sh /tmp/rollback_backend.sh && \
  CONFIRM_ROLLBACK=true API_PROJECT_DIR=/opt/air-api \
  API_BLUE_GREEN_SCRIPT=/tmp/deploy_backend_blue_green.sh \
  bash /tmp/rollback_backend.sh'
```

## Cloudflare Load Balancer

The monitor must use:

```text
Type: HTTPS
Path: /api/ready
Expected status: 200
Method: GET
```

Current desired pool order:

1. `mvn-api` origin, address `185.250.45.54`, host header `api.mvn.by`;
2. `zakup` origin, address `193.47.42.213`, host header `api.mvn.by`.

Fallback pool must be the current primary pool, not the standby pool. Cloudflare
fallback ignores health, so a fallback to standby can route users to an
unpromoted read-only API.

If Cloudflare still has old names such as `mvn-primary-zakup` and
`mvn-standby-api`, either rename them or verify by IP address. Names are less
important than order and fallback.

Repo-tracked Cloudflare config audit:

```bash
python3 scripts/ha/check_cloudflare_lb_config.py --env-file .env
```

Required environment:

```text
CLOUDFLARE_API_TOKEN_LB_AUDIT=<read-only token>
CLOUDFLARE_ZONE_ID=<mvn.by zone id>
CLOUDFLARE_ACCOUNT_ID=<Cloudflare account id>
```

The audit helper also accepts `CLOUDFLARE_LB_READ_TOKEN` and, for compatibility
with GitHub workflow env mapping, `CLOUDFLARE_API_TOKEN`. Locally prefer
`CLOUDFLARE_API_TOKEN_LB_AUDIT` so an old generic Cloudflare token cannot be
picked accidentally. This is a normal Cloudflare API token, separate from R2 S3
credentials. Create a custom read-only token from the Cloudflare API Tokens
screen and scope it to the `mvn.by` zone/account. Current Cloudflare role naming
exposes the relevant account-scoped role as **Load Balancing Account Read**,
which reads Load Balancers, Monitors, Monitor Groups, Pools, and Health Checks.

The audit calls these read-only endpoints, so the token must be able to read:

- zone load balancers, used for `GET /zones/{zone_id}/load_balancers`;
- account load balancing pools, used for
  `GET /accounts/{account_id}/load_balancers/pools`;
- account load balancing monitors, used for
  `GET /accounts/{account_id}/load_balancers/monitors`.

If the dashboard presents granular permission groups instead of roles, choose
read/list-only permissions for those same Load Balancing resources. Do not grant
edit permissions for this audit token.

For planned failover/failback, use a separate short-lived write token with
`Load Balancers Write`. The switch helper changes only `default_pools` and
`fallback_pool`; it does not edit origins, monitors, host headers, or pool
membership. Always run it without `--confirm` first:

```bash
printf 'Cloudflare LB write token: '
stty -echo
IFS= read -r CLOUDFLARE_LB_WRITE_TOKEN
stty echo
printf '\n'
export CLOUDFLARE_LB_WRITE_TOKEN
export CLOUDFLARE_ZONE_ID=<mvn.by zone id>
export CLOUDFLARE_ACCOUNT_ID=<Cloudflare account id>

# Current normal routing: mvn-api primary, zakup passive.
python3 scripts/ha/switch_cloudflare_lb_primary.py \
  --active-origin 185.250.45.54 \
  --passive-origin 193.47.42.213

# Apply only after the printed plan is correct.
python3 scripts/ha/switch_cloudflare_lb_primary.py \
  --active-origin 185.250.45.54 \
  --passive-origin 193.47.42.213 \
  --confirm

unset CLOUDFLARE_LB_WRITE_TOKEN
```

After the switch is applied and the required Cloudflare LB audit passes, revoke
or delete the short-lived write token. Do not store a token with `Load Balancers
Write` in `CLOUDFLARE_LB_READ_TOKEN`; the scheduled audit token must stay
read-only.

After a `zakup` promotion, reverse the origins:

```bash
printf 'Cloudflare LB write token: '
stty -echo
IFS= read -r CLOUDFLARE_LB_WRITE_TOKEN
stty echo
printf '\n'
export CLOUDFLARE_LB_WRITE_TOKEN
export CLOUDFLARE_ZONE_ID=<mvn.by zone id>
export CLOUDFLARE_ACCOUNT_ID=<Cloudflare account id>

python3 scripts/ha/switch_cloudflare_lb_primary.py \
  --active-origin 193.47.42.213 \
  --passive-origin 185.250.45.54
python3 scripts/ha/switch_cloudflare_lb_primary.py \
  --active-origin 193.47.42.213 \
  --passive-origin 185.250.45.54 \
  --confirm

unset CLOUDFLARE_LB_WRITE_TOKEN
```

GitHub scheduled audit fallback, if the helper above is not available:

```bash
gh secret set CLOUDFLARE_LB_READ_TOKEN --repo mvnby/air-api
gh variable set CLOUDFLARE_ZONE_ID --repo mvnby/air-api --body <zone-id>
gh variable set CLOUDFLARE_ACCOUNT_ID --repo mvnby/air-api --body <account-id>
gh workflow run check-cloudflare-lb-config.yml --repo mvnby/air-api --ref main -f required=true
# Set this only after the required workflow is green.
gh variable set CLOUDFLARE_LB_CONFIG_REQUIRED --repo mvnby/air-api --body true
```

Until those values exist, the scheduled workflow exits as skipped and does not
fail. After the read-only token is configured and the manual `required=true`
run is green, set `CLOUDFLARE_LB_CONFIG_REQUIRED=true`. From that point the
scheduled workflow fails if credentials disappear or config drifts, including
reversed pool order, fallback pointing to standby, missing Host header, or
monitor path changing away from `/api/ready`.

## Emergency Failover: `mvn-api` -> `zakup`

Use this only when `mvn-api` is actually unavailable or must be taken out.

Preferred helper path, run on `zakup` after copying
`deploy/ha/zakup/docker-compose.primary.yml` to
`/opt/mvn-reserve/docker-compose.primary.yml`:

```bash
ssh zakup 'OLD_PRIMARY_SSH=root@10.77.0.2 CONFIRM_PROMOTE=true /usr/local/sbin/mvn-promote-local-standby'
```

The helper is the source of truth for the host-local promotion mechanics. It
backs up the active standby compose file, copies
`docker-compose.primary.yml` over `docker-compose.reserve.yml`, starts `db`,
`app`, and `bot`, disables media pull, and verifies local `/api/ready`.

The helper refuses to promote without `OLD_PRIMARY_SSH` by default. If
`mvn-api` is unreachable and cannot be fenced over SSH, make that risk explicit:

```bash
ssh zakup 'ALLOW_UNFENCED_PROMOTE=true CONFIRM_PROMOTE=true /usr/local/sbin/mvn-promote-local-standby'
```

The manual steps below are the same procedure expanded for review.

1. Fence the old primary first if reachable:

   ```bash
   ssh mvn-api 'cd /opt/air-api && docker compose -f docker-compose.prod.yml stop app bot'
   ```

2. Confirm standby is caught up:

   ```bash
   ssh zakup /usr/local/sbin/mvn-standby-status
   ```

3. Promote `zakup`:

   ```bash
   ssh zakup 'cd /opt/mvn-reserve && docker compose -f docker-compose.reserve.yml exec -T db sh -lc '\''pg_ctl promote -D "$PGDATA"'\'''
   ```

4. Change `zakup` compose/runtime from standby to primary:

   - `APP_ROLE=primary`
   - `API_READY_ENABLED=true`
   - `SCHEDULER_ENABLED=true` in `app`
   - `BOT_ENABLED=false` in `app`
   - `BOT_ENABLED=true` and `SCHEDULER_ENABLED=false` in `bot`

   Use `deploy/ha/zakup/docker-compose.primary.yml` as the source of truth.
   Do not hand-edit the active compose file unless the prepared primary compose
   is missing. Back up the active standby compose and replace it with the
   prepared primary compose:

   ```bash
   ssh zakup 'cd /opt/mvn-reserve && cp docker-compose.reserve.yml "docker-compose.reserve.yml.pre-promote.$(date -u +%Y%m%d%H%M%S)" && cp docker-compose.primary.yml docker-compose.reserve.yml'
   ```

5. Start primary services on `zakup`:

   ```bash
   ssh zakup 'cd /opt/mvn-reserve && docker compose -f docker-compose.reserve.yml up -d app bot'
   ```

6. Disable media pull on the promoted primary:

   ```bash
   ssh zakup 'systemctl disable --now mvn-media-sync.timer mvn-media-sync.service'
   ```

7. Verify:

   ```bash
   curl -k --resolve api.mvn.by:443:193.47.42.213 https://api.mvn.by/api/ready
   ```

8. Update GitHub Actions variables and Cloudflare pool order/fallback to make
   `zakup` the current primary:

   ```bash
   python3 scripts/ha/switch_github_api_primary.py --repo mvnby/air-api --primary zakup
   python3 scripts/ha/switch_github_api_primary.py --repo mvnby/air-api --primary zakup --confirm

   printf 'Cloudflare LB write token: '
   stty -echo
   IFS= read -r CLOUDFLARE_LB_WRITE_TOKEN
   stty echo
   printf '\n'
   export CLOUDFLARE_LB_WRITE_TOKEN
   export CLOUDFLARE_ZONE_ID=<mvn.by zone id>
   export CLOUDFLARE_ACCOUNT_ID=<Cloudflare account id>
   python3 scripts/ha/switch_cloudflare_lb_primary.py \
     --active-origin 193.47.42.213 \
     --passive-origin 185.250.45.54
   python3 scripts/ha/switch_cloudflare_lb_primary.py \
     --active-origin 193.47.42.213 \
     --passive-origin 185.250.45.54 \
     --confirm
   unset CLOUDFLARE_LB_WRITE_TOKEN
   ```

   After the switch is verified, revoke/delete that write token. Keep
   `CLOUDFLARE_LB_READ_TOKEN` read-only for scheduled audits.

9. Do not restart `mvn-api` as primary. Rebuild it as standby from the promoted
   database.

GitHub Actions secret/variables after `zakup` promotion:

```text
SSH_HOST_API=193.47.42.213
API_PRIMARY_ORIGIN=193.47.42.213
API_STANDBY_ORIGIN=185.250.45.54
API_PROJECT_DIR=/opt/mvn-reserve
API_COMPOSE_FILE=docker-compose.reserve.yml
API_COMPOSE_SOURCE_FILE=deploy/ha/zakup/docker-compose.primary.yml
API_COPY_COMPOSE=true
API_DEPLOY_STRATEGY=in_place
API_BASE_URL=http://localhost:18000
API_READY_URL=http://localhost:18000/api/ready
API_LOCAL_HEALTH_URL=http://127.0.0.1:18000/api/health
API_TUNNEL_REMOTE_PORT=18000
API_DEPLOY_SERVICES=app bot
API_SMOKE_COMPOSE_SERVICE_CHECKS=app bot db
API_COMPOSE_SERVICE_CHECKS=app bot db
API_BOT_EXPECT_ENABLED=true
API_STANDBY_HOST=185.250.45.54
API_STANDBY_PROJECT_DIR=/opt/air-api
API_STANDBY_COMPOSE_FILE=docker-compose.prod.yml
API_STANDBY_COPY_COMPOSE=true
API_STANDBY_COMPOSE_SOURCE_FILE=deploy/ha/mvn-api/docker-compose.standby.yml
API_STANDBY_HEALTH_URL=http://localhost:8000/api/health
```

## Rebuild A Former Primary As Standby

Use this after every manual promotion. A former primary is considered divergent
until rebuilt from the new primary.

Required steps:

1. Stop old app, bot, and DB containers.
2. Save a tar archive of the old PostgreSQL volume for forensic comparison.
3. On the new primary:
   - expose PostgreSQL only on localhost and WireGuard;
   - create/update replication role `mvn_replicator`;
   - add a `pg_hba.conf` rule for the standby WireGuard IP;
   - create a physical replication slot for the standby.
4. On the standby:
   - remove the old PostgreSQL volume;
   - run `pg_basebackup -R -S <slot>`;
   - ensure `standby.signal` exists;
   - run DB with `max_connections >= primary max_connections`.
5. Start standby `db + app`.
6. Keep standby `bot` and scheduler disabled.
7. Set media sync to pull from the new primary to the standby.
8. Verify `/api/ready=503` on standby and replication slot active on primary.

## Restore Drill

Backups are stored in Google Drive. Freshness alone is not enough; periodically
prove that the latest DB dump restores.

Run on the current primary:

```bash
ssh mvn-api /usr/local/sbin/mvn-restore-drill-latest-db
```

The drill downloads the latest DB backup through the app container, starts a
disposable PostgreSQL container on the same Docker network, restores the dump
there, checks that public tables exist, and then removes the disposable
container. It does not touch the production or standby database.

GitHub also runs this daily:

```bash
gh workflow run api-restore-drill.yml --repo mvnby/air-api --ref main
```

## Hard Rules

- Never let both origins return `/api/ready=200`.
- Never run two writable PostgreSQL primaries.
- Never run Telegram polling on two hosts with the same token.
- Never run scheduler/import/payment jobs on standby.
- Never deploy a mutable backend image tag to production.
- Never update or recreate PostgreSQL as part of an application deploy.
- Never add a destructive Alembic change until all running and rollback-capable
  application versions tolerate the expanded schema.
- Never use bidirectional media sync.
- Never fail back by simply starting the old primary. Rebuild it as standby
  first, then promote intentionally if needed.
- `/api/health` is not a load-balancer health endpoint. Use `/api/ready`.

## Next Improvements

- Complete the staged Patroni migration described in
  `docs/postgres-quorum-runbook.md`; etcd installation alone must not be treated
  as automatic PostgreSQL failover.
