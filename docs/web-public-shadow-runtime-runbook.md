# Production Shadow Web Runtime Runbook

Related issue: #477

This runbook prepares an Astro Node runtime shadow on the current web VPS
without moving public `mvn.by` or `www.mvn.by` traffic away from the existing
static deployment.

## Guardrails

- No public apex/root cutover.
- No deletion of `/var/www/mvn.by/releases` or `/var/www/mvn.by/current`.
- No Cloudflare Load Balancing purchase/config.
- No broad Cloudflare cache changes.
- No DNS changes unless the manager explicitly approves them in the thread.
- The legacy `mvn-web` static fallback at `178.159.240.174` remains documented
  in `docs/deployment.md` and is not touched by this shadow workflow.

## Runtime Shape

- Compose service: `web-public-shadow`.
- Image: built locally on the web VPS from `/opt/air-api` at a recorded commit
  SHA.
- Bind: `127.0.0.1:4322:4321` only.
- Astro base path: `/`.
- API: `https://api.mvn.by/api/v1`.
- Public `mvn.by` static deploy/rebuild workflows stay unchanged.
- Optional protected nginx host route: `shadow-web.mvn.by`, basic-auth guarded,
  noindex, no-store, proxied to `127.0.0.1:4322`.

## GitHub Manual Deploy

Use the manual workflow:

```text
.github/workflows/deploy-web-shadow.yml
```

Inputs:

- `commit_sha`: commit to fetch/build on the VPS. Empty means the workflow run
  SHA.
- `dry_run`: default `true`; set `false` only when ready to mutate the shadow
  service.
- `run_local_smoke`: default `true`.
- `run_shadow_host_smoke`: default `false`; requires nginx shadow host route
  and the `WEB_SHADOW_BASIC_AUTH` secret.
- `run_public_static_smoke`: default `true`.

The workflow sends only a bounded script command over SSH. The web VPS fetches
the requested SHA, checks it out detached, builds `web-public-shadow`, starts it,
records `.web-public-shadow-deploy`, and runs selected smokes.

## Manual VPS Deploy

From the web VPS:

```bash
cd /opt/air-api
DEPLOY_SHA=<merged-or-approved-sha> \
DRY_RUN=true \
bash scripts/deploy_web_shadow.sh
```

Live shadow deploy:

```bash
cd /opt/air-api
DEPLOY_SHA=<merged-or-approved-sha> \
DRY_RUN=false \
RUN_LOCAL_SMOKE=true \
RUN_PUBLIC_STATIC_SMOKE=true \
bash scripts/deploy_web_shadow.sh
```

This builds and starts only:

```bash
docker compose -f docker-compose.web.yml up -d --build web-public-shadow
```

It does not reload public nginx, change DNS, change Cloudflare, or rsync/delete
static releases.

## Protected Origin Host Route

Install basic auth:

```bash
sudo apt-get install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd-web-shadow <user>
```

Install the origin-only host route:

```bash
sudo cp deployment/nginx/mvn-web-shadow-host.conf /etc/nginx/sites-available/mvn-web-shadow.conf
sudo ln -sfn /etc/nginx/sites-available/mvn-web-shadow.conf /etc/nginx/sites-enabled/mvn-web-shadow.conf
sudo nginx -t
sudo systemctl reload nginx
```

Origin-only smoke from the VPS, without DNS:

```bash
BASE_URL=http://127.0.0.1 \
HOST_HEADER=shadow-web.mvn.by \
BASIC_AUTH='<user>:<password>' \
REQUIRE_NOINDEX=true \
REQUIRE_NO_STORE=true \
REQUIRE_SSR_HEADERS=true \
bash scripts/smoke_web_public.sh
```

If a real protected shadow hostname is approved, add a Cloudflare DNS record and
TLS separately. Stop before changing DNS unless the manager explicitly approves.

Manual DNS shape after approval:

```text
Type: A
Name: shadow-web
Content: 153.80.244.78
Proxy status: Proxied
TTL: Auto
```

Equivalent Cloudflare API call to run only after approval:

```bash
curl -fsS -X POST "https://api.cloudflare.com/client/v4/zones/$CLOUDFLARE_ZONE_ID/dns_records" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"type":"A","name":"shadow-web","content":"153.80.244.78","proxied":true,"ttl":1}'
```

After DNS/TLS is approved and installed:

```bash
BASE_URL=https://shadow-web.mvn.by \
BASIC_AUTH='<user>:<password>' \
REQUIRE_NOINDEX=true \
REQUIRE_NO_STORE=true \
REQUIRE_SSR_HEADERS=true \
bash scripts/smoke_web_public.sh
```

## Required Smoke Plan

Local runtime on the VPS:

```bash
BASE_URL=http://127.0.0.1:4322 \
REQUIRE_SSR_HEADERS=true \
bash scripts/smoke_web_public.sh
```

Protected shadow route:

```bash
BASE_URL=http://127.0.0.1 \
HOST_HEADER=shadow-web.mvn.by \
BASIC_AUTH='<user>:<password>' \
REQUIRE_NOINDEX=true \
REQUIRE_NO_STORE=true \
REQUIRE_SSR_HEADERS=true \
bash scripts/smoke_web_public.sh
```

Public static storefront still OK:

```bash
BASE_URL=https://mvn.by bash scripts/smoke_web_public.sh
```

The public smoke includes:

- `/`
- `/catalog/`
- `/brands/`
- one product page
- one brand page
- one `/_astro/*` asset
- `https://api.mvn.by/api/health`
- `https://api.mvn.by/api/v1/catalog?limit=5`
- `https://api.mvn.by/api/v1/catalog/revision`
- `https://api.mvn.by/api/v1/filters/config`

## Rollback

Dry-run:

```bash
cd /opt/air-api
DRY_RUN=true bash scripts/rollback_web_shadow.sh
```

Stop only the shadow runtime:

```bash
cd /opt/air-api
DRY_RUN=false \
RUN_PUBLIC_STATIC_SMOKE=true \
bash scripts/rollback_web_shadow.sh
```

Stop the shadow runtime and disable the protected nginx host route:

```bash
cd /opt/air-api
DRY_RUN=false \
DISABLE_NGINX_SHADOW=true \
RUN_PUBLIC_STATIC_SMOKE=true \
bash scripts/rollback_web_shadow.sh
```

Rollback verification:

```bash
docker compose -f /opt/air-api/docker-compose.web.yml ps web-public-shadow
BASE_URL=https://mvn.by bash /opt/air-api/scripts/smoke_web_public.sh
curl -fsS https://api.mvn.by/api/health
```

This rollback is shadow-only. It leaves the public static release symlink,
release history, GitHub static deploy workflows, and legacy `mvn-web` fallback
unchanged.
