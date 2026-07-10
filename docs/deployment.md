# Deployment Guide

## Server Configuration

### Legacy Web Server / Fallback
- **Host alias:** `mvn-web`
- **User:** `user2154318`
- **IP:** `178.159.240.174`
- **Production path:** `/var/www/user2154318/data/www/mvn.by`
- **Dev path:** `/var/www/user2154318/data/www/dev.mvn.by`
- **SSH Key:** `~/.ssh/id_ed25519`
- **Role:** fallback static storefront target. Keep it available for rollback while the new VPS is monitored.

### Current Web VPS
- **Host alias:** `mvn`
- **User:** `deploy` for static deploys, `root` for server administration only
- **IP:** `153.80.244.78`
- **Hostname:** `www.mvn.by`
- **Production path:** `/var/www/mvn.by/current`
- **Nginx site:** `/etc/nginx/sites-available/mvn.by`
- **Role:** current public Astro storefront target for `mvn.by` and `www.mvn.by`.

Prepared server baseline:
- Ubuntu 24.04 LTS
- nginx serving `/var/www/mvn.by/current`
- UFW active with inbound `22/tcp`, `80/tcp`, and `443/tcp` allowed; other inbound traffic denied
- `deploy` user with SSH key auth and write access to the static root
- SSH password authentication disabled after root and deploy key login were verified
- fail2ban enabled for sshd
- unattended upgrades enabled
- Let's Encrypt certificate for `mvn.by` and `www.mvn.by` issued via Cloudflare DNS-01
- certbot renewal hook reloads nginx after certificate renewal

The production storefront is still static. The hybrid runtime/cache/freshness
design for the new VPS is documented in
[`web-runtime-freshness-runbook.md`](web-runtime-freshness-runbook.md). Do not
switch public `mvn.by` to Astro runtime without following that runbook's
staging, shadow, cutover, and rollback gates.

The production shadow runtime workflow for issue #477 is documented in
[`web-public-shadow-runtime-runbook.md`](web-public-shadow-runtime-runbook.md).
It binds the Astro runtime to `127.0.0.1:4322`, uses a protected/noindex
shadow host route, and keeps the public static root untouched.

Origin checks from a local machine:

```bash
ssh mvn true
ssh deploy@153.80.244.78 true
curl -fsS -H 'Host: mvn.by' http://153.80.244.78/healthz
curl -I -H 'Host: mvn.by' http://153.80.244.78/
curl -I --resolve mvn.by:443:153.80.244.78 https://mvn.by/
```

Cloudflare DNS state after the 2026-06-05 cutover:

```text
mvn.by      A 153.80.244.78 proxied
www.mvn.by  A 153.80.244.78 proxied
```

Rollback keeps using the legacy `mvn-web` server: restore the Cloudflare A records
to `178.159.240.174`, restore the legacy web deploy secrets if needed, and run the
manual web rebuild workflow.

### API Server
- **Host alias:** `mvn-api` for the original API VPS; `zakup` for the emergency API primary.
- **User:** `root`
- **Original API IP:** `185.250.45.54`
- **Emergency `zakup` IP:** `193.47.42.213`
- **SSH Key:** `~/.ssh/id_ed25519`
- **DNS:** `api.mvn.by` A-record must point to the current API primary.
- **GitHub secret:** `SSH_HOST_API` must point to the current API primary.
- **Public entrypoint:** reverse proxy on `80/443`, proxying `api.mvn.by` to the current API app port.
- **Health endpoint:** `/api/health`
- **Load balancer readiness endpoint:** `/api/ready`

The multi-origin API HA target and Cloudflare/DB/media runbook is documented in
[`api-ha-runbook.md`](api-ha-runbook.md). Use `/api/health` for basic smoke
checks and `/api/ready` for Cloudflare Load Balancer origin health.

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
| `API_DEPLOY_SERVICES` | `app bot` | Compose services to recreate after pulling images. |
| `API_BASE_URL` | `http://localhost:18080` | Stable nginx-local base URL used by post-deploy smoke. |
| `API_READY_URL` | `http://localhost:18080/api/ready` | Stable nginx-local readiness URL. |
| `API_SMOKE_COMPOSE_SERVICE_CHECKS` | `app bot` | Services expected to be running during smoke. |
| `API_BOT_EXPECT_ENABLED` | `true` | Whether smoke requires bot runtime controls to be enabled. |
| `API_TUNNEL_REMOTE_PORT` | `18080` | Stable nginx-local API port used by the frontend build SSH tunnel. |
| `API_COMPOSE_SERVICE_CHECKS` | `app bot db` | Services expected by the manual API VPS health workflow. |
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

## Local Deployment (Legacy)

Use the deployment script for local builds:

```bash
# Production deployment
./deploy_web.sh prod

# Dev deployment  
./deploy_web.sh dev
```

Local API/data scripts default to `root@185.250.45.54`. Override with `REMOTE_HOST=...` or `API_HOST=...` if you need a local SSH alias.

**What the script does:**
1. Builds frontend with production API data (`INTERNAL_API_URL` + `PUBLIC_API_URL`)
2. Syncs media from API server
3. Uploads `dist/` to web server via rsync
4. Configures robots.txt based on environment

**Critical:** Script uses `INTERNAL_API_URL=https://api.mvn.by/api/v1` during Astro static generation to fetch product data and generate all 102 static pages.

## GitHub Actions Deployment

### Release Trigger

The normal path is automatic: a successful `CI (Test & Lint)` run on `main`
starts `deploy.yml` for that exact commit. Failed or cancelled CI never starts a
production release.

For a manual replay:

1. Open https://github.com/mvnby/air-api/actions/workflows/deploy.yml.
2. Click **Run workflow**.
3. Select `main` only.
4. Choose whether to rebuild the storefront and run the workflow.

The release gate rejects a manual commit unless that exact SHA already has a
successful CI run.

### Environment Variables

The workflow requires these env vars in the build step:

```yaml
- name: Build Astro Site
  env:
    # Static generation: Production API for prerendered pages
    INTERNAL_API_URL: https://api.mvn.by/api/v1
    # Client-side: Production API
    PUBLIC_API_URL: https://api.mvn.by/api/v1
    # Google Tag Manager
    PUBLIC_GTM_ID: GTM-5CR6WBBC
```

**Without `INTERNAL_API_URL`:** Build generates only 16 pages (all API calls fail during static generation).
**With `INTERNAL_API_URL`:** Build generates 102+ pages (all products pre-rendered)

### Deployment Steps

1. **release-gate:** Resolves the tested `main` SHA and serializes production
   releases through the `production-release` concurrency group.
2. **deploy-backend:** Publishes `backend:<commit-sha>`, deploys its resolved
   `backend@sha256:<digest>` through the `production-api` environment, activates
   it through the inactive blue-green slot, and runs smoke checks.
3. **deploy-api-standby:** Installs the same image on the fenced app-only standby
   through the `standby-api` environment.
4. **deploy-frontend:** When web files changed (or manual rebuild was requested),
   builds Astro and deploys through the `production-web` environment.

The three GitHub environments are deployment audit boundaries. They contain no
new secrets by default; existing repository secrets remain the credential source.

### Backend Release Safety

Application release and database maintenance are separate lifecycles:

- `scripts/deploy_backend_blue_green.sh` starts the candidate on private port
  `18001` or `18002`, validates readiness/products/filters, and only then
  atomically reloads nginx to the candidate;
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

Automatic rollback restores the previous application image only when the failed
candidate was actually activated. It never downgrades the database schema. Use
expand/contract migrations so both the new image and retained rollback images
can run against the current schema.

The primary compose keeps the legacy `app` service on port `8000` only for the
first migration and emergency compatibility. Normal releases alternate between
profiled services `app-blue` and `app-green`. Nginx reads its active target from
`/etc/nginx/snippets/mvn-api-upstream.conf`; reload is graceful, so established
requests continue on the old worker while new requests move to the candidate.

Manual code rollback on the active API host:

```bash
scp scripts/deploy_backend_blue_green.sh scripts/rollback_backend.sh mvn-api:/tmp/
ssh mvn-api 'chmod +x /tmp/deploy_backend_blue_green.sh /tmp/rollback_backend.sh && \
  CONFIRM_ROLLBACK=true API_PROJECT_DIR=/opt/air-api \
  API_BLUE_GREEN_SCRIPT=/tmp/deploy_backend_blue_green.sh \
  bash /tmp/rollback_backend.sh'
```

### Web VPS Deploy Target

The web workflows deploy to the current VPS when these GitHub secrets are set:

```text
SSH_HOST_WEB=153.80.244.78
SSH_USER_WEB=deploy
SSH_WEB_TARGET=/var/www/mvn.by/current/
```

Legacy fallback values:

```text
SSH_HOST_WEB=178.159.240.174
SSH_USER_WEB=user2154318
SSH_WEB_TARGET=
```

Post-cutover verification:

1. Confirm `check-web-ssh.yml` succeeds against `deploy@153.80.244.78`.
2. Run `rebuild-web.yml` manually against the current VPS.
3. Verify the origin by IP with Host header:

   ```bash
   curl -I -H 'Host: mvn.by' http://153.80.244.78/
   curl -fsS -H 'Host: mvn.by' http://153.80.244.78/catalog/ | head
   ```

4. Verify public Cloudflare paths:

   ```bash
   curl -I https://mvn.by/
   curl -I https://mvn.by/catalog/
   curl -I https://www.mvn.by/
   ```

5. Roll back by restoring DNS and/or GitHub secrets to the legacy `mvn-web`
   values and running the manual rebuild workflow.

### Storefront Media Proxy

Backend-managed public media lives on the API host under `/media/...`, but
storefront content should prefer same-origin references such as
`/media/library/crop/example.webp`. The web VPS proxies those paths to the API
origin with the nginx snippet in
`deployment/nginx/mvn-media-proxy-location.conf`.

Install or refresh the snippet on the web VPS:

```bash
scp deployment/nginx/mvn-media-proxy-location.conf mvn:/etc/nginx/snippets/mvn-media-proxy-location.conf
ssh mvn
cp /etc/nginx/sites-available/mvn.by /etc/nginx/sites-available/mvn.by.bak-media-$(date +%Y%m%d%H%M%S)
# Include the snippet inside both mvn.by server blocks before the generic
# static asset regex location.
nginx -t
systemctl reload nginx
```

Origin smoke, bypassing Cloudflare:

```bash
curl -I -H 'Host: mvn.by' http://153.80.244.78/media/library/crop/<file>.webp
curl -I --resolve mvn.by:443:153.80.244.78 https://mvn.by/media/library/crop/<file>.webp
```

After enabling a new `/media/...` URL that previously returned 404 through
Cloudflare, purge that URL from Cloudflare cache or wait for the cached 404 to
expire. The Cloudflare token used for certbot DNS challenges may not have cache
purge permissions, so use a token with `Zone.Cache Purge` when clearing this
manually. Public smoke:

```bash
curl -I https://mvn.by/media/library/crop/<file>.webp
```

### Web SSH Reliability

`deploy-frontend` and the manual `rebuild-web.yml` workflow use bounded SSH port/login preflight checks before rsync. They retry 5 times with backoff and write a summary with separate `ssh_port_failures`, `ssh_login_failures`, `rsync_failures`, and `failure_kind` fields.

If `deploy-backend` and backend smoke-check are green but `deploy-frontend` fails with `failure_kind: web_ssh_connectivity`, treat it as web-host SSH/network instability from GitHub-hosted runners, not an Astro/backend build failure.

Use the manual **Web SSH Connectivity Check** workflow to probe `SSH_HOST_WEB` from GitHub Actions without building or deploying files. If the probe is flaky too, the next decision should be architectural rather than adding more retries:

- move the static site to a managed static hosting/CDN deploy path;
- move web hosting to infrastructure with stable SSH from GitHub Actions;
- switch to a pull-based deploy where the web host fetches a release artifact instead of GitHub Actions opening inbound SSH to the host.

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

## Safety Checks 🛡️

To prevent deploying an empty site (when API is down or config is wrong), we added a pre-build check:

**Script:** `web/scripts/check-api.js`

**Logic:**
1. Checks config endpoint (`/config`)
2. Checks catalog endpoint (`/catalog?limit=1`)
3. **Fails build if:** 
   - API is unreachable
   - Product count is 0

**Integration:**
Configured in `web/package.json`:
```json
"scripts": {
  "check-api": "node scripts/check-api.js",
  "build": "npm run check-api && astro build"
}
```
If `check-api` fails, `astro build` will NOT run, protecting the production site.

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

### Issue: Catalog shows "Товары не найдены"

**Symptoms:**
- Only 16 pages in build logs
- API fetch errors during build: `[API] Fetch error for http://app:8000/api/v1/...`

**Root cause:** Missing `INTERNAL_API_URL` in build environment

**Fix:** Ensure `INTERNAL_API_URL=https://api.mvn.by/api/v1` is set before `npm run build`

### Issue: Browser cache showing old version

**Fix:** Hard refresh
- **Mac:** `Cmd + Shift + R`
- **Windows:** `Ctrl + Shift + R`

### Issue: web SSH or rsync timeout

**Symptoms:** `ssh: connect to host ... port 22: Connection timed out`, `rsync error: unexplained error (code 255)`, or deploy summary `failure_kind: web_ssh_connectivity`.

**Checks:** Confirm whether backend deploy and smoke-check were green, then run the manual **Web SSH Connectivity Check** workflow. A flaky probe means the web SSH path is unstable before file transfer starts.

**Fix direction:** Do not keep increasing retries. Pick a more reliable deploy architecture: managed static hosting/CDN, web hosting with stable SSH from GitHub Actions, or pull-based artifact deployment from the web host.

## Verification

After deployment, check:

1. **Build logs:** Should show `102 page(s) built` (not 16)
2. **Catalog:** https://mvn.by/catalog/ should display products
3. **Product pages:** https://mvn.by/product/[slug]/ should work
4. **Console:** No GTM errors (`gtm.js?id=undefined`)
5. **API calls:** Should go to `https://api.mvn.by/api/v1/...` (not `https://mvn.by/api/v1/...`)
