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

Expected deploy behavior:

- primary `mvn-api`: recreate `app` and `bot`;
- standby `zakup`: recreate only `app`, then stop `bot`;
- frontend deploy is skipped unless explicitly requested.

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
