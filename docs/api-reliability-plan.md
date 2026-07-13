# API Reliability Plan

Related issue: #429

This plan is a decision document for the earlier single-VPS/passive-reserve API
stage after the public raw Postgres and FastAPI ports were closed and after
single-active runtime controls were added for the scheduler and Telegram bot.
The current multi-origin HA target lives in
[`api-ha-runbook.md`](api-ha-runbook.md). This document remains useful as
background and for single-VPS migration context.

Related repo artifacts:

- [Deployment guide](deployment.md)
- [API single-VPS migration runbook](api-vps-migration-runbook.md)
- [API VPS monitoring runbook](api-vps-monitoring.md)
- [Product media R2/S3 migration notes](media-storage-r2.md)
- [`docker-compose.prod.yml`](../docker-compose.prod.yml)
- [`scripts/deploy.sh`](../scripts/deploy.sh)
- [`scripts/post_deploy_smoke_check.sh`](../scripts/post_deploy_smoke_check.sh)
- [`scripts/check_api_vps_health.sh`](../scripts/check_api_vps_health.sh)
- [`services/backup_service.py`](../services/backup_service.py)
- [`services/scheduler_service.py`](../services/scheduler_service.py)
- [`core/runtime_controls.py`](../core/runtime_controls.py)

## Current Production Shape

The current API production model is one Docker Compose origin at
`/opt/air-api`:

- `db`: PostgreSQL 15, volume `postgres_data`, bound to `127.0.0.1:5432`.
- `app`: FastAPI, manager UI, static/media serving, in-process scheduler
  loops, bound to `127.0.0.1:8000`.
- `bot`: Telegram bot polling process.
- nginx terminates public `api.mvn.by` traffic and proxies to
  `127.0.0.1:8000`.
- Public smoke checks use `/api/health`, `/api/v1/products?limit=5`, and
  `/api/v1/filters/config`.

Known hosts from current docs:

| Role | Host/IP | Notes |
| --- | --- | --- |
| Current API | `mvn-api`, `185.250.45.54` | Current API origin and deploy target. |
| Current web | `mvn`, `153.80.244.78` | Public Astro storefront for `mvn.by` and `www.mvn.by`. |
| API standby | `zakup`, `193.47.42.213` | Warm application and PostgreSQL standby; remains fenced until promotion. |
| Legacy web host | `mvn-web`, `178.159.240.174` | Stale historical copy; do not treat as a verified rollback target. |

Deploy path constraints:

- A production release starts only after successful CI on `main` (or a manual
  dispatch that proves the same commit already passed CI).
- The backend workflow publishes
  `ghcr.io/mvnby/air-api/backend:<commit-sha>` and deploys the resolved
  `backend@sha256:<digest>` artifact.
- `scripts/deploy.sh` pulls only application images, runs Alembic/defaults in a
  one-off `--no-deps` container, and recreates only `app`/`bot` with
  `--no-deps`; PostgreSQL is not touched by application deployment.
- The same tested image is then installed on the fenced `zakup` app-only
  standby, followed by an active-passive invariant check.
- Failed activation/smoke triggers a guarded code rollback. Database migrations
  remain forward-only and must be expand/contract compatible.

Runtime single-active controls:

- Missing or empty `APP_ROLE` defaults to `primary`.
- `APP_ROLE=primary` or `active` enables scheduler/bot unless explicitly
  disabled.
- `APP_ROLE=standby`, `passive`, `readonly`, `read-only`, or `read_only`
  disables scheduler/bot unless explicitly enabled.
- `SCHEDULER_ENABLED=false` keeps scheduler loops disabled even on primary.
- `BOT_ENABLED=false` keeps Telegram polling disabled even on primary.
- A mistakenly started standby `bot` container idles instead of polling.

## Recommendation

For a small Belarus-hosted business site/API, use option 2:

1. Move the API primary to the new Belarus VPS using the existing
   single-VPS migration runbook.
2. Keep the old API VPS as a passive reserve for a defined rollback window.
3. Keep `mvn-web` as storefront reserve separately from API reliability.
4. Add owner-visible monitoring and backup-restore drills before investing in
   Cloudflare Load Balancing or active failover.

This gives the owner control over the hosting/provider choice, keeps the system
simple enough for the current Docker Compose/Postgres/local-media model, and
uses the single-active controls added for #433/#449. Full active failover is
possible later, but it should wait until database replication, media/object
storage, deploy routing, and bot/scheduler promotion are designed as one system.

## Topology Options

### Option 1: Current API VPS Plus Monitoring

Topology:

```text
Cloudflare/api.mvn.by -> nginx on current API VPS -> localhost app -> local db
                                                        |
                                                        +-> bot polling
                                                        +-> scheduler loops
                                                        +-> local /media
                                                        +-> Google Drive backups/docs
```

Cost, complexity, risk:

| Dimension | Estimate |
| --- | --- |
| Incremental infra cost | Lowest: no second API VPS required. |
| Complexity | Low: current deploy path and runbooks remain unchanged. |
| Outage recovery | Manual restore or manual VPS repair. RTO is hours if the host is lost. |
| Data-loss risk | Bounded by latest good DB/media backup unless the old disk is recoverable. |
| Operational risk | Low day-to-day, but high during provider/VPS outage. |

Implementation:

- Keep current `SSH_HOST_API=185.250.45.54`.
- Keep `APP_ROLE=primary` or unset, `SCHEDULER_ENABLED` unset/true,
  `BOT_ENABLED` unset/true.
- Run the manual GitHub **API VPS Health Check** workflow in `ssh` mode after
  deploys and incidents.
- Add one owner-approved alert path:
  - external cron public check every 5 minutes, or
  - scheduled GitHub Actions health check, or
  - uptime service checking the three public endpoints.
- Run a monthly restore drill to a non-public disposable host or local Docker
  volume using the latest Drive DB/media backup.

When to choose:

- Choose this only if the current API provider is acceptable and the owner wants
  to spend effort on monitoring/runbooks before migration.

When not to choose:

- Do not choose this if provider geography/control is the main concern, because
  monitoring will detect an outage but will not reduce failover work.

### Option 2: New Belarus API Primary Plus Passive Reserve

Topology after cutover:

```text
Cloudflare/api.mvn.by -> nginx on new BY API VPS -> localhost app -> local db
                                                         |
                                                         +-> bot polling
                                                         +-> scheduler loops
                                                         +-> local /media
                                                         +-> Google Drive backups/docs

Old API VPS: stopped app/bot or standby app-only, no public writes.
Legacy mvn-web: separate static storefront rollback target.
```

Cost, complexity, risk:

| Dimension | Estimate |
| --- | --- |
| Incremental infra cost | Medium: one new API VPS; keep old API VPS during rollback window. |
| Complexity | Medium: one planned migration, manual DNS/GitHub secret changes. |
| Outage recovery | Faster than option 1 if old API remains intact; still manual. |
| Data-loss risk | Low during planned cutover; emergency rollback can diverge after writes. |
| Operational risk | Best fit for current single-DB/local-media architecture. |

Recommended state:

- New BY VPS becomes the only active API primary.
- Old API VPS remains powered and untouched for at least one full backup cycle
  plus a business-approved rollback window.
- Old API `app`/`bot` stay stopped after cutover, or old API runs only
  app-only standby checks with:

  ```dotenv
  APP_ROLE=standby
  SCHEDULER_ENABLED=false
  BOT_ENABLED=false
  ```

- Do not route public writes to the reserve host.

Planned migration steps:

1. Select `COMMIT_SHA` from a green backend deploy and confirm the image exists
   in GHCR.
2. Prepare the new VPS baseline: Docker, Compose, nginx, firewall, TLS, and
   `/opt/air-api`.
3. Copy runtime files from old API to new API without printing secrets:
   `.env`, `docker-compose.prod.yml`, the `google-oauth/` directory,
   `client_secret.json`, and `credentials.json`. Retain a legacy `token.json`
   only as a temporary rollback artifact.
4. Create `docker-compose.cutover.yml` on the new host with the SHA-pinned
   backend image.
5. Start only `db` on the new host.
6. Enter a maintenance freeze: no manager edits, imports, orders, uploads,
   restore jobs, or Telegram bot actions.
7. Stop old `bot` and old `app`; leave old `db` running only for the final dump.
8. Take a final frozen `pg_dump --clean --if-exists` and `media.tar.gz`.
9. Transfer the dump and media archive to the new VPS.
10. Restore DB and media on the new VPS.
11. Run `alembic upgrade head` and `scripts/ensure_global_config_defaults.py`
    in one-off app containers.
12. Set primary runtime controls on the new VPS:

    ```dotenv
    APP_ROLE=primary
    SCHEDULER_ENABLED=true
    BOT_ENABLED=true
    ```

13. Start new `app` only.
14. Verify app logs contain `Scheduler startup enabled`.
15. Run localhost and nginx-origin smoke checks on the new VPS:

    ```bash
    curl -fsS http://127.0.0.1:8000/api/health
    curl -fsS "http://127.0.0.1:8000/api/v1/products?limit=5"
    curl -fsS http://127.0.0.1:8000/api/v1/filters/config
    curl -fsS -H 'Host: api.mvn.by' http://127.0.0.1/api/health
    ```

16. If TLS is ready before DNS cutover, test with `curl --resolve`.
17. Update Cloudflare `api.mvn.by` A record to the new IP.
18. Update GitHub `SSH_HOST_API` to the new IP.
19. Run public smoke checks from outside the VPS.
20. Start new `bot` only after public smoke is green.
21. Run final public smoke and the full API VPS health check against the new
    primary.

Rollback:

1. Stop new `bot` and `app`.
2. Set the new host back to standby env if it will remain powered:

   ```dotenv
   APP_ROLE=standby
   SCHEDULER_ENABLED=false
   BOT_ENABLED=false
   ```

3. Point Cloudflare `api.mvn.by` back to the old API IP.
4. Restore GitHub `SSH_HOST_API` to the old API IP if it was changed.
5. Start old `app` and `bot`.
6. Run public smoke checks.
7. If the new API accepted writes before rollback, decide explicitly whether to
   back-transfer DB/media from new to old or accept losing those writes.

Standby refresh after cutover:

- Keep the reserve host stale by default unless the owner accepts the data-loss
  bound. A stale standby is still valuable for rehearsing deploy/restore, but it
  must not be advertised as no-data-loss failover.
- If the owner wants a warmer reserve, run a scheduled, owner-approved refresh:
  restore latest Drive DB/media backups into the reserve while `APP_ROLE=standby`
  and with no public traffic.
- After each refresh, run app-only standby checks, not the full primary health
  script, because `scripts/check_api_vps_health.sh` expects `app`, `bot`, and
  `db` all running for full SSH mode.

When to choose:

- Choose this now because the owner has already selected a new Belarus-hosted
  VPS and the repo has the needed single-active controls and migration runbook.

### Option 3: Cloudflare Load Balancing Or Active Failover

Possible target topology:

```text
Cloudflare Load Balancer/api.mvn.by
  |-- primary API origin -> app + bot + scheduler + primary writable db
  `-- standby API origin -> app-only checks + replicated/restored db

Shared/replicated state:
  - DB through managed Postgres, streaming replication, or tested backup restore
  - product media through R2/S3 or bidirectional sync with conflict rules
  - Google Drive documents through shared Drive account and DB file ids
```

Cost, complexity, risk:

| Dimension | Estimate |
| --- | --- |
| Incremental infra cost | Highest: second API host plus paid load balancing or equivalent. |
| Complexity | High: replication, health semantics, deployment, and promotion logic. |
| Outage recovery | Potentially minutes for app-origin failure after full design. |
| Data-loss risk | Low only with real DB replication and shared media; otherwise backup-age bound. |
| Operational risk | High until failover and rollback are rehearsed. |

Required before safe use:

- A database design:
  - managed Postgres with automated backups and failover, or
  - PostgreSQL streaming replication with a documented promotion/fencing
    procedure, or
  - explicit backup-age-based standby with owner-accepted RPO.
- Media design:
  - move product media/originals to object storage, or
  - implement one-way primary-to-standby sync with freeze/promotion rules.
- Deploy design:
  - GitHub deploy must know which host is primary, or deploy must publish an
    artifact that each host pulls safely by role.
- Health design:
  - primary health must include public API, DB, scheduler/bot expected state,
    disk/inodes, TLS, and backup freshness.
  - standby health must be app-only or read-only and must verify scheduler/bot
    are disabled.
- Promotion design:
  - exactly one host may run scheduler loops.
  - exactly one host may poll Telegram.
  - public write traffic must not hit two writable databases.

When to choose:

- Choose this later if the business needs automatic API failover and is willing
  to pay for the extra monthly services and operational rehearsals.

When not to choose:

- Do not choose it as the immediate next step. With local Postgres, local media,
  and one-host GitHub deploy, Cloudflare origin failover alone can route traffic
  to stale or inconsistent state.

## Data Recovery Plan

### Database

Current backup path:

- Production scheduler runs daily backup at 03:00 when `ENVIRONMENT=production`
  and scheduler loops are enabled.
- `services.backup_service.BackupService.perform_backup(cleanup=True)` creates
  a SQL dump with `pg_dump --clean --if-exists`, creates a `media/` archive,
  uploads both to Google Drive, rotates to the latest 10 backup sets, and removes
  local backup files.
- Backup freshness is checked by `scripts/check_api_vps_health.sh` from inside
  the running app container.

Recovery rules:

- For planned migration, prefer a final frozen dump from the old `db` after old
  `app` and `bot` are stopped. Drive backup is a secondary recovery source.
- For emergency recovery, use the latest Drive DB backup only after checking age
  and confirming the owner accepts possible data loss since that backup.
- Always run `alembic upgrade head` and
  `scripts/ensure_global_config_defaults.py` after restoring to a host that may
  run a newer image.
- Keep at least one tested restore target that is not public production.

Recommended restore test:

1. Run `scripts/check_api_vps_health.sh` with `CHECK_BACKUPS=true`.
2. Pick the latest DB and media backups from `backup_service.list_backups`.
3. Restore DB into a disposable local Docker volume or standby host.
4. Restore media archive to a disposable `/opt/air-api/media`.
5. Start `db` and app-only `app` with:

   ```dotenv
   APP_ROLE=standby
   SCHEDULER_ENABLED=false
   BOT_ENABLED=false
   ```

6. Run:

   ```bash
   curl -fsS http://127.0.0.1:8000/api/health
   curl -fsS "http://127.0.0.1:8000/api/v1/products?limit=5"
   curl -fsS http://127.0.0.1:8000/api/v1/filters/config
   docker compose -f docker-compose.prod.yml logs --tail=120 app | grep 'Scheduler startup skipped'
   ```

7. Record backup timestamps, restore duration, smoke result, and any manual
   repair needed.

### Product Media

Current state:

- `docker-compose.prod.yml` mounts `./media:/app/media`.
- FastAPI serves `/media` from the local `media/` directory.
- Daily backup includes a tar archive of `media/`.
- `docs/media-storage-r2.md` documents only generated variant migration to
  R2/S3-compatible storage. Original product image fields remain local
  `/media/...` URLs during that transition.
- `PRODUCT_MEDIA_STORAGE_PROVIDER` defaults to `local`.

Reliability implication:

- A standby without refreshed `media/` may return product records whose image
  URLs 404.
- R2 variant migration helps cache/generated variants but is not a complete
  failover story for originals yet.
- Do not delete local media after R2 variant rollout until a separate owner
  decision covers original media storage and rollback.

Recommended next state:

- For option 2, copy `media/` during migration and keep the old API media
  directory untouched through the rollback window.
- For standby refresh, restore both DB and media from the same backup generation
  when possible.
- For option 3, decide whether product originals also move to R2/S3 or whether
  there will be one-way media sync from primary to standby.

### Documents And Google Drive

Current state:

- Generated order documents, uploaded order documents, customer contracts, and
  document downloads use Google Drive file ids and edit URLs stored in the DB.
- The app needs Google credential files in production. The refreshable OAuth
  token uses the writable directory contract
  `google-oauth/token.json -> /app/google-oauth/token.json`; client secret and
  service credentials remain read-only runtime files.
- The migration runbook already treats these credential files as runtime files
  that must be copied to the new VPS without printing contents.

Reliability implication:

- DB backup preserves references to documents, but the actual document bytes
  live in Google Drive.
- A restored API host must have valid Google credentials or manager document
  generation/download/upload flows will fail even if DB restore succeeds.
- Google Drive outage is a separate dependency; API failover does not remove it.

Recommended checks:

- During migration preflight, verify Google auth status in the manager UI or run
  a safe list operation through the app container.
- During restore drills, list backups and, if approved, test one non-critical
  document export/download path.
- Keep credential file permissions tight and never copy credential contents into
  workflow logs.

## Monitoring Checklist

Minimum near-term monitoring:

- Public check every 5 minutes from outside the API VPS:

  ```bash
  bash scripts/check_api_vps_health.sh --public-only
  ```

- Full SSH check hourly from a trusted runner:

  ```bash
  API_SSH_HOST=mvn-api API_SSH_USER=root bash scripts/check_api_vps_health.sh
  ```

- Keep `BACKUP_MAX_AGE_HOURS=36` unless the owner changes the backup schedule.
- Alert on:
  - public health/products/filters failure;
  - DB not online in health payload;
  - `app`, `bot`, or `db` not running on primary;
  - disk or inode critical usage;
  - TLS certificate expiry under critical threshold;
  - latest DB or media backup older than threshold.

Recommended alert routing:

- Pick one primary owner-visible channel: GitHub Actions failure notification,
  mailbox, Telegram, Slack, Discord, or uptime provider.
- Pick one fallback channel that does not depend on the failed API host.
- Do not include env dumps, tokens, DB passwords, Drive folder IDs, or private
  key material in alerts.

Post-deploy checklist:

1. Backend deploy summary is green.
2. `scripts/post_deploy_smoke_check.sh` passed.
3. Public `scripts/check_api_vps_health.sh --public-only` passed.
4. Full SSH API VPS check passed.
5. Backup freshness shows both `db` and `media` fresh.
6. App logs show scheduler enabled only on primary.
7. Bot logs show polling only on primary.

## Proposed Follow-Up Issues

These are not required before option 2 migration, but they would reduce manual
risk:

- Add a scheduled API health workflow or document the chosen external cron
  runner and alert channel.
- Add a standby/app-only mode to `scripts/check_api_vps_health.sh` so standby
  validation does not fail because `bot` is intentionally stopped.
- Add a restore-drill checklist or script that records backup age, restore time,
  and smoke result without touching production.
- Decide whether product originals should move to R2/S3 or whether standby media
  sync is enough.
- Continue evolving the current recreate step into a blue-green application
  switch after the release gate and rollback baseline is proven in production.
- Continue from the implemented streaming-replication/Cloudflare active-passive
  baseline toward quorum-based automatic PostgreSQL failover only after fencing
  and failure drills are automated.

## Owner Decisions Still Needed

- New API VPS IP, SSH user model, root/deploy access policy, OS image, disk
  size, backup/snapshot option, and provider support/SLA.
- Migration window and maximum acceptable API/bot downtime.
- Rollback window duration and whether to keep the old API VPS for one billing
  cycle or longer.
- Alerting channel and who receives alerts outside business hours.
- Whether GitHub Actions health checks should become scheduled or stay manual.
- Whether to buy/use Cloudflare Load Balancing or keep manual DNS rollback.
- R2/S3 bucket/domain decision for product media variants, and later whether
  original media should also leave local disk.
- Whether emergency failover may lose writes since the last backup, or whether
  the business requires DB replication before failover is advertised.
