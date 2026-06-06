# Astro SSR Staging Spike Runbook

Related issue: #464

This spike proves the Astro Node runtime on the new web VPS without moving the
public `mvn.by` production root away from the current static deploy.

## Guardrails

- Public production `mvn.by` remains static from `/var/www/mvn.by/current`.
- Existing `web/astro.config.mjs`, `npm run build`, `deploy.yml`, and
  `rebuild-web.yml` keep their static behavior.
- The SSR runtime is exposed only under `/__ssr-staging/` and should be guarded
  by basic auth or an IP allowlist.
- The first spike uses public `https://api.mvn.by/api/v1` for both build-time
  prerendering and runtime SSR fetches.

## What This PR Implements

- `web/astro.config.ssr.mjs`: separate Astro Node standalone server config.
- `web/package.json`: explicit `build:ssr:staging`, `start:ssr:staging`, and
  `smoke:ssr:staging` scripts.
- `web/Dockerfile.prod`: builds the staging SSR server output; static GitHub
  Actions deploys do not use this image path.
- `docker-compose.web.yml`: localhost-bound Docker Compose service for the
  staging Node runtime.
- `deployment/nginx/mvn-ssr-staging-location.conf`: hidden nginx location
  snippet for `/__ssr-staging/`.
- `web/scripts/smoke-ssr-staging.mjs`: smoke checks for `/`, `/catalog/`, a
  query catalog URL, `/brands/`, one product URL, and one `/_astro/*` asset.

## Route Policy

Prerendered/static in the staging SSR build:

- `/`
- product detail pages under `/product/[slug]`
- service pages and service landing pages
- brand detail pages under `/brands/[slug]`
- popular catalog SEO pages under `/catalog/[virtual]`
- blog, legal, cart, checkout, success, contact, and static content shells

Runtime SSR in the staging build:

- `/catalog/`
- `/catalog/?...` query pages
- `/brands/`

This is intentionally conservative. It gives the spike a real request-time
freshness path for catalog and brand lists while preserving the most important
SEO/static entry points.

## Local Smoke

From `web/`:

```bash
INTERNAL_API_URL=https://api.mvn.by/api/v1 \
PUBLIC_API_URL=https://api.mvn.by/api/v1 \
SSR_STAGING_BASE_PATH=/__ssr-staging \
npm run build:ssr:staging

HOST=127.0.0.1 PORT=4321 npm run start:ssr:staging
```

In another shell:

```bash
SSR_SMOKE_BASE_URL=http://127.0.0.1:4321/__ssr-staging \
SSR_SMOKE_API_URL=https://api.mvn.by/api/v1 \
npm run smoke:ssr:staging
```

If the API catalog lookup should not choose the product automatically, set:

```bash
SSR_SMOKE_PRODUCT_PATH=/product/<known-slug>/ npm run smoke:ssr:staging
```

## Web VPS Staging Deploy

On the new web VPS:

```bash
cd /opt/air-api
git pull
SSR_INTERNAL_API_URL=https://api.mvn.by/api/v1 \
PUBLIC_API_URL=https://api.mvn.by/api/v1 \
PUBLIC_SITE_URL=https://mvn.by \
SSR_STAGING_BASE_PATH=/__ssr-staging \
SSR_STAGING_PORT=4321 \
docker compose -f docker-compose.web.yml up -d --build web-ssr-staging
```

The service binds to `127.0.0.1:4321`; do not expose it directly to the public
internet.

Install the nginx snippet inside the existing `mvn.by` server block:

```bash
cp deployment/nginx/mvn-ssr-staging-location.conf /etc/nginx/snippets/mvn-ssr-staging-location.conf
sed -i '/server_name mvn.by www.mvn.by;/a\\    include /etc/nginx/snippets/mvn-ssr-staging-location.conf;' /etc/nginx/sites-available/mvn.by
nginx -t
systemctl reload nginx
```

Run origin smoke:

```bash
SSR_SMOKE_BASE_URL=http://127.0.0.1:4321/__ssr-staging \
npm --prefix web run smoke:ssr:staging
```

Run hidden nginx smoke from an allowed/authenticated context:

```bash
SSR_SMOKE_BASE_URL=https://mvn.by/__ssr-staging \
SSR_SMOKE_BASIC_AUTH='<user>:<password>' \
SSR_SMOKE_PRODUCT_PATH=/product/<known-slug>/ \
npm --prefix web run smoke:ssr:staging
```

## Hybrid Freshness Design

High-freshness public data:

- product price and old price;
- product availability and stock-derived status;
- product publication state;
- catalog membership and sort order;
- brand/product list counts.

Current spike behavior:

- `/catalog/`, query catalog pages, and `/brands/` fetch from the API at request
  time in the Node runtime.
- Product detail pages remain prerendered for SEO/performance; client-side price
  and availability refresh remains a safety layer, but detail HTML freshness is
  not promoted in this issue.
- Corrected prices and publication changes should be validated through catalog
  and brand list pages before any public SSR cutover.

Follow-up freshness work to investigate:

- API/catalog revision endpoint, for example `/api/v1/catalog/revision`, bumped
  by manager writes that affect public catalog output.
- SSR data cache keyed by revision plus route/query, with short TTL fallback.
- Explicit invalidation trigger from manager after price, availability,
  publication, or product-list updates.
- Product detail runtime mode or partial hydration strategy that prevents
  unpublished products and corrected prices from lingering in initial HTML.

Suggested initial cache rules for future promotion:

- `/_astro/*`: `Cache-Control: public, max-age=31536000, immutable`.
- SSR HTML containing price, availability, or publication state: start with
  `Cache-Control: public, s-maxage=60, stale-while-revalidate=300` or bypass
  Cloudflare until behavior is measured.
- Query catalog pages: `noindex,follow` and bypass or very short edge TTL.
- Cart, checkout, lead/order POSTs, API, and manager paths: no edge caching.
- During the hidden staging spike: nginx sends `Cache-Control: no-store`.

## Static Rollback Retention

Keep at least three static releases on disk:

```text
/var/www/mvn.by/releases/<timestamp-a>
/var/www/mvn.by/releases/<timestamp-b>
/var/www/mvn.by/releases/<timestamp-c>
/var/www/mvn.by/current -> /var/www/mvn.by/releases/<active>
```

Fast rollback to static-only:

```bash
cd /var/www/mvn.by
ln -sfn /var/www/mvn.by/releases/<known-good> current
rm -f /etc/nginx/snippets/mvn-ssr-staging-location.conf
nginx -t
systemctl reload nginx
cd /opt/air-api
docker compose -f docker-compose.web.yml stop web-ssr-staging
```

Then smoke the static production root:

```bash
curl -I https://mvn.by/
curl -I https://mvn.by/catalog/
curl -I https://www.mvn.by/
```

The existing manual `rebuild-web.yml` workflow remains the GitHub rollback path
for rebuilding and rsyncing static `web/dist/` to `SSH_WEB_TARGET`.
