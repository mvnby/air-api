# Deployment Guide

## Server Configuration

### Storefront service

The public storefront is a separate service owned by
[`mvnby/mvn-web`](https://github.com/mvnby/mvn-web). Its SSR runtime, DNS,
Cloudflare, web-VPS access, rollback tooling and public smoke checks are not
managed from this API repository. The API interacts with it only through the
public HTTP contract and the signed catalog-rebuild callback.

### API Server
- **Host alias:** `mvn-api` for the original API VPS; `zakup` for the emergency API primary.
- **User:** `root`
- **Original API IP:** `185.250.45.54`
- **Emergency `zakup` IP:** `193.47.42.213`
- **SSH Key:** `~/.ssh/id_ed25519`
- **Routing:** `api.mvn.by` is managed by Cloudflare Load Balancing; `/api/ready`
  controls which origin receives traffic.
- **GitHub secret:** `SSH_HOST_API` identifies the physical-mode deployment host.
  Patroni mode probes both protected deployment environments instead.
- **Public entrypoint:** reverse proxy on `80/443`, proxying `api.mvn.by` to the current API app port.
- **Health endpoint:** `/api/health`
- **Load balancer readiness endpoint:** `/api/ready`

The multi-origin API HA target and Cloudflare/DB/media runbook is documented in
[`api-ha-runbook.md`](api-ha-runbook.md). Use `/api/health` for basic smoke
checks and `/api/ready` for Cloudflare Load Balancer origin health.

Google OAuth refresh state uses a writable directory mount, not a bind-mounted
file. Prepare and verify it with
[`google-oauth-token-runbook.md`](google-oauth-token-runbook.md) before manual
deployments; automated deploy paths run the same fail-closed preparation.

The backend deploy workflow is primary-host configurable. Keep sensitive values
in GitHub secrets and non-secret routing values in GitHub variables.

Required API secrets:

| Name | Purpose |
| --- | --- |
| `SSH_HOST_API` | Current API primary host/IP. |
| `SSH_USER_API` | SSH user for the API host. |
| `SSH_KEY` | Private deploy key. |
| `GHCR_PAT` | Token used by the VPS to pull backend images from GHCR. |

Optional API variables:

| Name | Default | Purpose |
| --- | --- | --- |
| `API_PROJECT_DIR` | `/opt/air-api` | Directory containing `.env`, compose file, media, and runtime files. |
| `API_COMPOSE_FILE` | `docker-compose.prod.yml` | Compose file name inside `API_PROJECT_DIR`. |
| `API_COPY_COMPOSE` | `true` | Copy repo `docker-compose.prod.yml` to the host before deploy. Set `false` for host-local emergency compose. |
| `API_DEPLOY_STRATEGY` | `blue_green` | `blue_green` on `mvn-api`; use `in_place` on the shared `zakup` fallback. |
| `API_DEPLOY_SERVICES` | `app` | Compose services to recreate after pulling images. The Telegram polling service deploys independently. |
| `API_BASE_URL` | `http://localhost:18080` | Stable nginx-local base URL used by post-deploy smoke. |
| `API_READY_URL` | `http://localhost:18080/api/ready` | Stable nginx-local readiness URL. |
| `API_SMOKE_COMPOSE_SERVICE_CHECKS` | `app` | API services expected to be running during smoke. |
| `API_BOT_EXPECT_ENABLED` | `false` | Legacy compatibility switch; production API deploys do not own Telegram polling. |
| `API_TUNNEL_REMOTE_PORT` | `18080` | Stable nginx-local API port used by the frontend build SSH tunnel. |
| `API_COMPOSE_SERVICE_CHECKS` | `app db` | Services expected by the manual API VPS health workflow. |
| `API_LOCAL_HEALTH_URL` | `http://127.0.0.1:18080/api/health` | Host-local health URL for the manual API VPS health workflow. |

Current emergency `zakup` values:

```text
SSH_HOST_API=193.47.42.213
SSH_USER_API=root
API_PROJECT_DIR=/opt/mvn-reserve
API_COMPOSE_FILE=docker-compose.reserve.yml
API_DEPLOY_STRATEGY=in_place
API_COPY_COMPOSE=false
API_DEPLOY_SERVICES=app
API_BASE_URL=http://localhost:18000
API_READY_URL=http://localhost:18000/api/ready
API_SMOKE_COMPOSE_SERVICE_CHECKS=app db
API_BOT_EXPECT_ENABLED=false
API_TUNNEL_REMOTE_PORT=18000
API_COMPOSE_SERVICE_CHECKS=app db
API_LOCAL_HEALTH_URL=http://127.0.0.1:18000/api/health
```

This keeps the emergency Caddy/network compose on `zakup` intact while still
allowing backend image deploys from `main`.

Production compose binds backend-only ports to localhost:

```yaml
db:
  ports:
    - "127.0.0.1:5432:5432"
app:
  ports:
    - "127.0.0.1:8000:8000"
app-blue:
  ports:
    - "127.0.0.1:18001:8000"
app-green:
  ports:
    - "127.0.0.1:18002:8000"
```

This prevents direct internet access to Postgres and every raw FastAPI port.
Nginx exposes a stable private proxy on `127.0.0.1:18080`; deploys alternate the
two profiled slots and never recreate `db`. The legacy `app` service is removed
after the first successful blue-green activation.

### API Runtime Roles

The backend image has single-active runtime controls for future standby work.
Current production does not need new env values: missing `APP_ROLE`,
empty `APP_ROLE`, empty `SCHEDULER_ENABLED`, and empty `BOT_ENABLED` are treated
as the active primary default.

| Host mode | Services | Required env | Behavior |
| --- | --- | --- | --- |
| Primary/current production | `db`, `app`, `bot` | `APP_ROLE=primary` or unset; `SCHEDULER_ENABLED`/`BOT_ENABLED` unset or `true` | FastAPI starts scheduler loops; bot starts Telegram polling. |
| Standby/passive API | `db`, `app` only | `APP_ROLE=standby`, `SCHEDULER_ENABLED=false`, `BOT_ENABLED=false` | FastAPI serves passive health/API checks without scheduler loops; bot must not be started. If started accidentally, it idles without polling. |

During a blue-green overlap, an eligible API slot becomes ready without waiting
for the scheduler advisory lock. Its background supervisor waits and starts the
scheduler once the previous slot releases the lock. PostgreSQL runtime locks use
one pinned `AUTOCOMMIT` connection for their full lifetime, so they are never
returned to the pool while held and do not leave an idle transaction open. The
scheduler probes that connection at least every five seconds while it runs; a
probe is bounded to three seconds so a blackholed backend also stops the current
loop. Ownership loss, a probe deadline, or an unexpected scheduler-loop exit is
fail-stop: the API process records `faulted`, cancels the loop, and immediately
sends itself `SIGKILL`. Docker restarts the container, which also guarantees that
threads and subprocesses such as an in-flight backup cannot survive as a second
scheduler owner. This is the safe temporary boundary until scheduler jobs move
to a dedicated service with durable per-job fencing. A new owner holds the lock
through a minimum twelve-second fencing grace before starting loops. Deployment
also bounds scheduler-owner container shutdown to five seconds before Docker
force-kills it. The fencing delay is therefore longer than both that kill
deadline and the previous release's default shutdown/liveness window, including
the first rollout where the old image does not yet have shutdown fail-stop.
Normal application shutdown also sends `SIGKILL` before cancellation or runtime
lock release once scheduler work has started. This applies even when the asyncio
task already looks done or cancelled: cancellation of an `asyncio.to_thread`
call does not stop its worker thread, and a cooperative unlock could otherwise
let the next API slot start scheduler work while the old process is still
draining. Shutdown remains graceful while the supervisor is only waiting for the
lock or in the fencing delay, because no scheduler work has started in those
states.
`/api/ready.scheduler_runtime` exposes only the allowlisted ownership state;
blue-green activation requires six consecutive `running` samples after the old
slot has stopped and a monotonic stability window of at least nine seconds.
Lowering the polling delay cannot shorten that safety window. Scheduler locking
is fail-closed:
`RUNTIME_DB_LOCKS_ENABLED=false` or a non-PostgreSQL database keeps scheduler
loops stopped instead of permitting multiple owners.

Catalog import startup is conservative: it may schedule a `queued` job only
when the database contains no `running` job. A `running` job is never
automatically moved back to `queued`, because the current job record has no
durable owner lease proving that its worker is dead. Operators must investigate
such a job; lease, heartbeat, and stale-owner reclaim remain a separate upgrade.

Rollback after the old slot has already stopped uses the third free API slot as
an API-only buffer. A temporary Compose override starts the previous image with
database bootstrap, scheduler, and bot disabled; nginx routes to that ready
buffer before the candidate is stopped. The old slot can then acquire the free
scheduler lock and start normally. The buffer is removed only after a ready old
slot, or a ready candidate with a stable scheduler, has received traffic. If
neither recovers within the bounded checks, the managed buffer remains the live
route and its override is preserved as `.rollback-api-buffer.compose.yml` for
operator inspection instead of leaving a dead upstream.

`SCHEDULER_ENABLED` and `BOT_ENABLED` are explicit overrides. If either is set
to `false`, that process stays disabled even when `APP_ROLE=primary`; remove the
override or set it to `true` before promoting a standby host.

`API_READY_ENABLED` controls whether `/api/ready` may return HTTP 200 for public
traffic. It follows `APP_ROLE` by default. Set `API_READY_ENABLED=true` only on
the origin that Cloudflare may route to. Set it to `false`, or leave it unset
with `APP_ROLE=standby`, on reserve origins.

These controls do not enable Cloudflare load balancing, automatic failover, or
public standby cutover. Do not route public write traffic to a standby host.

Passive standby smoke, without changing Cloudflare or enabling failover:

```bash
ssh <standby-api-host>
cd /opt/air-api
printf '\nAPP_ROLE=standby\nSCHEDULER_ENABLED=false\nBOT_ENABLED=false\n' >> .env
docker compose -f docker-compose.prod.yml up -d db app
docker compose -f docker-compose.prod.yml stop bot || true
docker compose -f docker-compose.prod.yml logs --tail=120 app | grep 'Scheduler startup skipped'
curl -fsS http://127.0.0.1:8000/api/health
```

Before merging or deploying a compose hardening change, save the current
production compose file:

```bash
ssh mvn-api
cd /opt/air-api
cp docker-compose.prod.yml docker-compose.prod.yml.bak-public-ports-$(date +%Y%m%d%H%M%S)
```

After the hardened compose file is deployed, apply the DB binding and verify:

```bash
ssh mvn-api
cd /opt/air-api
docker compose -f docker-compose.prod.yml up -d db
curl -fsS https://api.mvn.by/api/health
curl -fsS http://127.0.0.1:18080/api/health
nc -vz 185.250.45.54 5432 # should fail from outside
nc -vz 185.250.45.54 8000 # should fail from outside
```

Rollback is a compose-file restore plus container recreate:

```bash
ssh mvn-api
cd /opt/air-api
cp docker-compose.prod.yml.bak-public-ports-<timestamp> docker-compose.prod.yml
docker compose -f docker-compose.prod.yml up -d --force-recreate db app bot
curl -fsS http://127.0.0.1:8000/api/health
```

## GitHub Actions Deployment

### Release Trigger

The normal path is automatic: a successful `CI (Test & Lint)` run on `main`
starts `deploy.yml` for that exact commit. Failed or cancelled CI never starts a
production release.

For a manual replay:

1. Open https://github.com/mvnby/air-api/actions/workflows/deploy.yml.
2. Click **Run workflow**.
3. Select `main` only.
4. Run the API workflow.

The release gate rejects a manual commit unless that exact SHA already has a
successful CI run.

### Deployment Steps

1. **release-gate:** Resolves the tested `main` SHA and serializes production
   releases through the `production-release` concurrency group.
2. **backend deployment:** Publishes one immutable `backend@sha256:<digest>`.
   Physical mode deploys `production-api` then the fenced standby. After the
   guarded Patroni cutover, role-aware mode probes both nodes, migrates only on
   the current primary, updates the fenced replica, then blue-greens the primary.
3. **backend-release:** Requires exactly one physical or Patroni deployment path
   to succeed. It never publishes storefront files.
4. **standalone storefront:** `mvnby/mvn-web` owns its immutable SSR image,
   shadow deployment, catalog synchronization, and public cutover. The last
   atomic static release remains available as an nginx rollback target.

The three GitHub environments are deployment audit boundaries. They contain no
new secrets by default; existing repository secrets remain the credential source.

### Backend Release Safety

Application release and database maintenance are separate lifecycles:

- `scripts/deploy_backend_blue_green.sh` starts the candidate on private port
  `18001` or `18002`, validates readiness/products/filters, and only then
  atomically reloads nginx to the candidate;
- under the deployment lock, the active container's immutable
  `Config.Image` is the rollback source of truth; normal deploys reconcile
  `.env` to it before mutations, while bootstrap validation fails on drift;
- the `already_active` shortcut also requires a matching running bot image, no
  preserved rollback buffer, and a scheduler that passes the monotonic
  stability gate; otherwise the normal activation path repairs the release;
- the previous API slot remains available during validation and is stopped only
  after origin and public readiness pass; `.active-api-slot` records the result;
- `scripts/deploy.sh` remains the app-only standby deploy path; both scripts use
  `--no-deps`, and post-deploy ops never call `compose up`;
- the compose PostgreSQL image is pinned to an explicit version and digest;
- changing `POSTGRES_IMAGE` requires a planned database maintenance window,
  backup/replication checks, and its own rollback plan;
- production backend tags must end in a 40-character Git SHA (or a sha256
  digest); mutable `latest` tags are rejected;
- the server deployment lock prevents overlapping releases;
- cleanup retains three backend releases and never runs a global
  `docker system prune -af`.

Before compose promotion, failed-candidate recovery restores the active runtime
image and canonical compose together under the same deployment lock. After the
Google token-directory migration, manual rollback accepts only images labeled
with the `directory-v1` token contract and requires a durable Google backup probe;
pre-hotfix images fail closed and must be replaced by a roll-forward release.
Rollback never downgrades the database schema. Use expand/contract migrations so
all retained directory-compatible images can run against the current schema.

The primary compose keeps the legacy `app` service on port `8000` only for the
first migration and emergency compatibility. Normal releases alternate between
profiled services `app-blue` and `app-green`. Nginx reads its active target from
`/etc/nginx/snippets/mvn-api-upstream.conf`; reload is graceful, so established
requests continue on the old worker while new requests move to the candidate.

Manual code rollback on the active API host:

```bash
scp scripts/deploy_backend_blue_green.sh scripts/deploy_backend_blue_green_safety.sh \
  scripts/prepare_google_oauth_token_dir.sh scripts/rollback_backend.sh mvn-api:/tmp/
ssh mvn-api 'chmod +x /tmp/deploy_backend_blue_green.sh \
  /tmp/deploy_backend_blue_green_safety.sh /tmp/prepare_google_oauth_token_dir.sh \
  /tmp/rollback_backend.sh && \
  CONFIRM_ROLLBACK=true API_PROJECT_DIR=/opt/air-api \
  API_BLUE_GREEN_SCRIPT=/tmp/deploy_backend_blue_green.sh \
  API_BLUE_GREEN_SAFETY_HELPER=/tmp/deploy_backend_blue_green_safety.sh \
  GOOGLE_OAUTH_TOKEN_PREPARE_SCRIPT=/tmp/prepare_google_oauth_token_dir.sh \
  bash /tmp/rollback_backend.sh'
```

This command refuses an unlabeled pre-hotfix image. It also restores the current
image automatically if the post-activation Google durability probe fails.

The old `deploy_api.sh` source-bind path is intentionally retired. Production
changes must use the CI-tested immutable-image workflow.

### Storefront boundary

The API publisher and the embedded storefront source were removed after the
standalone `mvn-web` CI and production deployment had been proven. Active
storefront deployment, rollback and catalog revision verification live only in
`mvnby/mvn-web`. The API dispatch target is controlled by
`WEB_REBUILD_GITHUB_OWNER`, `WEB_REBUILD_GITHUB_REPO`, and
`WEB_REBUILD_GITHUB_REF`.

## Manager Frontend Env Model

`manager_frontend` is built inside GitHub Actions and then embedded into the backend Docker image.
Because of that, its public URLs are controlled by build-time env, not by `/opt/air-api/.env` on the server.

Current source of truth:

- **Local dev:** root `.env` or `.env.development.local`
- **Production deploy:** `.github/workflows/deploy.yml`

Important details:

- Vite reads root env files because `manager_frontend/vite.config.ts` uses `envDir: '../'`.
- `env.prod` is legacy and is no longer part of the active deployment path.
- For local-safe defaults, `.env.example` now uses `WEBSITE_URL=http://localhost:4321`.
- If you need a local override without touching `.env`, copy `.env.development.local.example` to `.env.development.local`.

For production manager builds, set `WEBSITE_URL` explicitly in the workflow step that runs `npm run build`.

## Post-Deploy Data Ops (Brands/Categories)

When release includes normalization or brand/category sync changes, run data ops in safe mode first:

```bash
# 1) Dry-run backfill + safe cleanup (no commit)
APP_SERVICE="app-$(cat /opt/air-api/.active-api-slot)"
docker compose -f /opt/air-api/docker-compose.prod.yml --profile bluegreen exec -T "${APP_SERVICE}" \
  python3 scripts/backfill_brand_series.py --dry-run --safe-brand-cleanup

# 2) Apply only after dry-run review
docker compose -f /opt/air-api/docker-compose.prod.yml --profile bluegreen exec -T "${APP_SERVICE}" \
  python3 scripts/backfill_brand_series.py --safe-brand-cleanup
```

Optional automation through `ops_post_deploy.sh`:

```bash
RUN_POST_DEPLOY_OPS=true \
RUN_BACKFILL_BRAND_SERIES=true \
RUN_SAFE_BRAND_CLEANUP=true \
OPS_MODE=report_only \
bash scripts/ops_post_deploy.sh
```

After apply, smoke-check:
- `/api/health`
- `/api/v1/products?limit=5`
- `/api/v1/filters/config`

## API VPS Monitoring

Use `scripts/check_api_vps_health.sh` for cheap API VPS monitoring and runbook
checks. It validates the public API endpoints, and when SSH is configured it
also checks disk/inodes, Docker services, Postgres readiness, localhost app
health, nginx TLS expiry, and Google Drive backup freshness from inside the app
container.

```bash
# Public API only, safe from any machine
bash scripts/check_api_vps_health.sh --public-only

# Full VPS + backup freshness checks from a trusted machine
API_SSH_HOST=mvn-api API_SSH_USER=root bash scripts/check_api_vps_health.sh
```

See `docs/api-vps-monitoring.md` for cron examples, the manual GitHub Actions
workflow, alert routing options, and failure triage.

## API VPS Reliability Strategy

Use `docs/api-reliability-plan.md` to choose between current single-VPS
monitoring, a new Belarus API primary with passive reserve, and future
Cloudflare Load Balancing or active failover. It captures the DB, bot/scheduler,
media, documents, DNS rollback, monitoring, and owner-decision tradeoffs for
issue #429.

## Product Media R2/S3 Rollout

Product image variant storage can be switched from local files to R2/S3-compatible
storage with `PRODUCT_MEDIA_STORAGE_PROVIDER=r2`. Keep it `local` until the
owner approves rollout and the dry-run migration report has been reviewed.

See `docs/media-storage-r2.md` for URL strategy, cache/versioning behavior,
manual migration commands, secrets checklist, and rollback notes.

## Common Issues

## Verification

After an API deployment, verify `/api/health`, `/api/ready`,
`/api/v1/products?limit=5`, and `/api/v1/filters/config`. Storefront release
and public-page verification belong to the `mvn-web` deployment workflow.
