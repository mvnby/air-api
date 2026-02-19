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
- **IP:** `89.39.120.97`
- **SSH Key:** `~/.ssh/id_ed25519`

## Local Deployment (Legacy)

Use the deployment script for local builds:

```bash
# Production deployment
./deploy_web.sh prod

# Dev deployment  
./deploy_web.sh dev
```

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
2. **deploy-frontend:** Builds Astro site, uploads to web server via SCP

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

### Issue: rsync connection timeout

**Symptoms:** `rsync: error: unexpected end of file`

**Fix:** Use GitHub Actions deployment instead of local rsync for large updates

## Verification

After deployment, check:

1. **Build logs:** Should show `102 page(s) built` (not 16)
2. **Catalog:** https://mvn.by/catalog/ should display products
3. **Product pages:** https://mvn.by/product/[slug]/ should work
4. **Console:** No GTM errors (`gtm.js?id=undefined`)
5. **API calls:** Should go to `https://api.mvn.by/api/v1/...` (not `https://mvn.by/api/v1/...`)
