# API HA Runbook

This runbook describes the current active-passive API setup for `api.mvn.by`.
The system intentionally has one writable PostgreSQL primary and one warm
standby. Do not make both origins public-writable.

Last verified state: 2026-07-02.

## Current Hosts

| Host | SSH alias | Current role | API path | API port |
| --- | --- | --- | --- | --- |
| Original API VPS | `mvn-api` | Active primary | `/opt/air-api` | `127.0.0.1:8000` |
| Belarus reserve VPS | `zakup` | Warm standby | `/opt/mvn-reserve` | `127.0.0.1:18000` |
| Web VPS | `mvn` | Storefront only | n/a | n/a |

Current data direction:

```text
mvn-api PostgreSQL primary 10.77.0.2:5432
  -> zakup PostgreSQL physical standby 10.77.0.1:5432, slot zakup_standby

mvn-api /opt/air-api/media
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
| Local standby promotion helper | `scripts/ha/promote_local_standby.sh` |
| Disposable DB restore drill | `scripts/ha/restore_drill_latest_db.sh` |
| PostgreSQL PITR WAL/basebackup upload | `scripts/ha/upload_postgres_pitr_to_s3.py`, `scripts/ha/upload_postgres_pitr_wal.sh`, `scripts/ha/create_postgres_pitr_basebackup.sh` |
| PostgreSQL PITR env configuration | `scripts/ha/configure_postgres_pitr_env.py` |
| PostgreSQL PITR monitoring | `scripts/ha/check_postgres_pitr_status.sh`, `scripts/ha/check_postgres_pitr_remote.py`, `.github/workflows/check-postgres-pitr.yml` |
| PostgreSQL PITR systemd units | `deploy/ha/systemd/mvn-postgres-wal-upload.*`, `deploy/ha/systemd/mvn-postgres-basebackup.*` |
| Status helpers | `scripts/ha/mvn-primary-status.sh`, `scripts/ha/mvn-standby-status.sh` |
| Media sync helper/timer | `scripts/ha/media_sync_pull.sh`, `deploy/ha/systemd/mvn-media-sync.*` |

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

GitHub health check:

```bash
gh workflow run check-api-vps-health.yml --repo mvnby/air-api --ref main -f mode=ssh
```

Scheduled monitors:

| Workflow | Schedule | Purpose |
| --- | --- | --- |
| `check-api-vps-health.yml` | every 6 hours | primary host, containers, DB, backups |
| `check-api-ha-invariants.yml` | every 30 minutes | public/primary ready and standby fenced |
| `api-restore-drill.yml` | daily after the 03:00 UTC backup | disposable DB restore drill |
| `check-postgres-pitr.yml` | every 6 hours | PITR archive/timer/backlog and remote R2 freshness |

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

# Put the private R2 credentials in a temporary root-only file on the primary.
# Do not paste these values in tickets, PRs, or chat.
ssh mvn-api 'umask 077; cat > /root/mvn-postgres-pitr.env' <<'EOF'
POSTGRES_PITR_CLUSTER=mvn-api
POSTGRES_PITR_S3_BUCKET=<private-r2-bucket>
POSTGRES_PITR_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
POSTGRES_PITR_S3_REGION=auto
POSTGRES_PITR_S3_ACCESS_KEY_ID=<private-r2-token-access-key>
POSTGRES_PITR_S3_SECRET_ACCESS_KEY=<private-r2-token-secret>
POSTGRES_PITR_S3_KEY_PREFIX=postgres/pitr
EOF

# Write PITR credentials into /opt/air-api/.env with a backup. This keeps
# POSTGRES_PITR_ARCHIVE_MODE=off until upload is proven.
ssh mvn-api '/usr/local/sbin/mvn-postgres-pitr-configure-env --project-dir /opt/air-api --input-env-file /root/mvn-postgres-pitr.env'
ssh mvn-api 'rm -f /root/mvn-postgres-pitr.env'

# Prove private bucket upload with a physical basebackup first. This is a real
# upload; it does not require archive_mode yet.
ssh mvn-api 'PROJECT_DIR=/opt/air-api COMPOSE_FILE=docker-compose.prod.yml /usr/local/sbin/mvn-postgres-pitr-basebackup'

# Then explicitly enable archive settings in /opt/air-api/.env with another
# backup. This does not take effect until the db container is recreated.
ssh mvn-api '/usr/local/sbin/mvn-postgres-pitr-configure-env --project-dir /opt/air-api --enable-archive'

# In a short maintenance window, recreate db so archive_mode=on and the
# /postgres-wal-archive mount become active.
ssh mvn-api 'cd /opt/air-api && docker compose -f docker-compose.prod.yml up -d --force-recreate db'

# Clear historical archiver counters after the planned recreate so strict
# monitoring starts from the current PITR setup, not from earlier dry-run
# mistakes that have already been investigated.
ssh mvn-api 'cd /opt/air-api && docker compose -f docker-compose.prod.yml exec -T db sh -lc '\''psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}"'\''' <<'SQL'
select pg_stat_reset_shared('archiver');
SQL

# Force one WAL switch and prove WAL upload before enabling timers permanently.
ssh mvn-api 'cd /opt/air-api && docker compose -f docker-compose.prod.yml exec -T db sh -lc '\''psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -c "select pg_switch_wal();"'\'''
ssh mvn-api 'PROJECT_DIR=/opt/air-api COMPOSE_FILE=docker-compose.prod.yml /usr/local/sbin/mvn-postgres-pitr-upload-wal'

# Then enable recurring PITR.
ssh mvn-api 'systemctl enable --now mvn-postgres-wal-upload.timer mvn-postgres-basebackup.timer'

# Finally make the scheduled GitHub PITR check strict.
gh variable set POSTGRES_PITR_REQUIRED --repo mvnby/air-api --body true
```

Quick PITR status:

```bash
ssh mvn-api 'PROJECT_DIR=/opt/air-api COMPOSE_FILE=docker-compose.prod.yml PITR_REQUIRED=true /usr/local/sbin/mvn-postgres-pitr-status'
ssh mvn-api 'cd /opt/air-api && docker compose -f docker-compose.prod.yml exec -T db sh -lc '\''psql -U "$POSTGRES_USER" -d "${POSTGRES_DB:-air_conditioners}" -c "select archived_count,last_archived_wal,last_archived_time,failed_count,last_failed_wal,last_failed_time from pg_stat_archiver;"'\'''
ssh mvn-api 'systemctl list-timers --all | grep mvn-postgres'
```

Manual GitHub monitor run:

```bash
gh workflow run check-postgres-pitr.yml --repo mvnby/air-api --ref main -f required=true
```

Point-in-time restore outline:

1. Pick the latest basebackup before the target timestamp from
   `postgres/pitr/<cluster>/basebackups/*/manifest.json`.
2. Restore `base.tar.gz` and `pg_wal.tar.gz` into a clean PostgreSQL data
   directory.
3. Provide a `restore_command` that fetches archived WAL from
   `postgres/pitr/<cluster>/wal/<timeline>/%f`.
4. Set `recovery_target_time` to the target timestamp and start PostgreSQL with
   `recovery.signal`.
5. Validate the restored DB in an isolated container before replacing any
   production role.

The repo currently contains upload and basebackup automation. A full
one-command PITR restore helper is intentionally a separate step because restore
must be rehearsed against real private bucket credentials without touching
production.

## GitHub Actions Routing

Current production variables must match the active primary:

```text
SSH_HOST_API=185.250.45.54
API_PROJECT_DIR=/opt/air-api
API_COMPOSE_FILE=docker-compose.prod.yml
API_COMPOSE_SOURCE_FILE=deploy/ha/mvn-api/docker-compose.primary.yml
API_COPY_COMPOSE=true
API_BASE_URL=http://localhost:8000
API_READY_URL=http://localhost:8000/api/ready
API_LOCAL_HEALTH_URL=http://127.0.0.1:8000/api/health
API_TUNNEL_REMOTE_PORT=8000
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

If an emergency requires manual host-local compose edits, set
`API_COPY_COMPOSE=false` and/or `API_STANDBY_COPY_COMPOSE=false` temporarily.
Switch back to the repo-tracked files after the emergency is resolved.

Manual deploy verification:

```bash
gh workflow run deploy.yml --repo mvnby/air-api --ref main -f deploy_frontend=false
```

The workflow builds and pushes both `backend:latest` and
`backend:<commit_sha>`, but production deploys must run the immutable
`backend:<commit_sha>` tag through `BACKEND_IMAGE`. This keeps primary and
standby on the same image for the same deployment.

Expected deploy behavior:

- primary `mvn-api`: recreate `app` and `bot`;
- standby `zakup`: recreate only `app`, then stop `bot`;
- both API hosts: prune unused Docker images after successful deploy; this does
  not remove volumes or images used by running containers;
- frontend deploy is skipped unless explicitly requested.

Manual disk pressure check:

```bash
ssh mvn-api 'df -h / && docker system df'
ssh zakup 'df -h / && docker system df'
```

Manual emergency image cleanup, safe for databases and media volumes:

```bash
ssh mvn-api 'docker image prune -af && df -h /'
ssh zakup 'docker image prune -af && df -h /'
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

## Emergency Failover: `mvn-api` -> `zakup`

Use this only when `mvn-api` is actually unavailable or must be taken out.

Preferred helper path, run on `zakup` after copying
`deploy/ha/zakup/docker-compose.primary.yml` to
`/opt/mvn-reserve/docker-compose.primary.yml`:

```bash
ssh zakup 'OLD_PRIMARY_SSH=root@10.77.0.2 CONFIRM_PROMOTE=true /usr/local/sbin/mvn-promote-local-standby'
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
   `zakup` the current primary.

9. Do not restart `mvn-api` as primary. Rebuild it as standby from the promoted
   database.

GitHub Actions variables after `zakup` promotion:

```text
SSH_HOST_API=193.47.42.213
API_PROJECT_DIR=/opt/mvn-reserve
API_COMPOSE_FILE=docker-compose.reserve.yml
API_COMPOSE_SOURCE_FILE=deploy/ha/zakup/docker-compose.primary.yml
API_COPY_COMPOSE=true
API_BASE_URL=http://localhost:18000
API_READY_URL=http://localhost:18000/api/ready
API_LOCAL_HEALTH_URL=http://127.0.0.1:18000/api/health
API_TUNNEL_REMOTE_PORT=18000
API_DEPLOY_SERVICES=app bot
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
- Never use bidirectional media sync.
- Never fail back by simply starting the old primary. Rebuild it as standby
  first, then promote intentionally if needed.
- `/api/health` is not a load-balancer health endpoint. Use `/api/ready`.

## Next Improvements

- Add Cloudflare API automation for pool order/fallback changes.
- Add owner-visible alerts from GitHub Actions or Cloudflare to Telegram/email
  beyond the default GitHub failed-workflow notification path.
