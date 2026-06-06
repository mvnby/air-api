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
- **Host alias:** `mvn-api`
- **User:** `root`
- **IP:** `185.250.45.54`
- **SSH Key:** `~/.ssh/id_ed25519`
- **DNS:** `api.mvn.by` A-record must point to `185.250.45.54`
- **GitHub secret:** `SSH_HOST_API` must be `185.250.45.54`
- **Public entrypoint:** nginx on `80/443`, proxying `api.mvn.by` to `127.0.0.1:8000`
- **Health endpoint:** `/api/health`

Production compose binds backend-only ports to localhost:

```yaml
db:
  ports:
    - "127.0.0.1:5432:5432"
app:
  ports:
    - "127.0.0.1:8000:8000"
```

This keeps nginx and SSH-tunnel workflows working while preventing direct
internet access to Postgres and the raw FastAPI port. The normal backend deploy
recreates `app` and `bot`, so the app binding change is applied by the deploy.
The `db` container is intentionally not force-recreated on every deploy; apply
the DB port binding during a short maintenance window.

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
curl -fsS http://127.0.0.1:8000/api/health
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

### Manual Trigger

1. Go to: https://github.com/mvnby/air-api/actions/workflows/deploy.yml
2. Click "Run workflow"
3. **IMPORTANT:** Select correct branch (e.g., `filter-by-specs-and-bulk-update`)
4. Click green "Run workflow" button

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

1. **deploy-backend:** Builds and pushes Docker image, deploys to API server
2. **deploy-frontend:** Builds Astro site, uploads to web server via rsync over SSH

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
docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app \
  python3 scripts/backfill_brand_series.py --dry-run --safe-brand-cleanup

# 2) Apply only after dry-run review
docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app \
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
