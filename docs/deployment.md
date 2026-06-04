# Deployment Guide

## Server Configuration

### Web Server
- **Host alias:** `mvn-web`
- **User:** `user2154318`
- **IP:** `178.159.240.174`
- **Production path:** `/var/www/user2154318/data/www/mvn.by`
- **Dev path:** `/var/www/user2154318/data/www/dev.mvn.by`
- **SSH Key:** `~/.ssh/id_ed25519`

### API Server
- **Host alias:** `mvn-api`
- **User:** `root`
- **IP:** `185.250.45.54`
- **SSH Key:** `~/.ssh/id_ed25519`
- **DNS:** `api.mvn.by` A-record must point to `185.250.45.54`
- **GitHub secret:** `SSH_HOST_API` must be `185.250.45.54`

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

**Critical:** Script uses `INTERNAL_API_URL=https://api.mvn.by/api/v1` for SSR build to fetch product data and generate all 102 static pages.

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
    # SSR Build: Production API for static generation
    INTERNAL_API_URL: https://api.mvn.by/api/v1
    # Client-side: Production API
    PUBLIC_API_URL: https://api.mvn.by/api/v1
    # Google Tag Manager
    PUBLIC_GTM_ID: GTM-5CR6WBBC
```

**Without `INTERNAL_API_URL`:** Build generates only 16 pages (all API calls fail during SSR)  
**With `INTERNAL_API_URL`:** Build generates 102+ pages (all products pre-rendered)

### Deployment Steps

1. **deploy-backend:** Builds and pushes Docker image, deploys to API server
2. **deploy-frontend:** Builds Astro site, uploads to web server via rsync over SSH

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
- `/health`
- `/api/v1/products?limit=5`
- `/api/v1/filters/config`

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
