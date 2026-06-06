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
- `web/src/utils/api.js`: staging-only catalog revision freshness context,
  in-process GET cache keyed by `catalog_revision + URL`, and diagnostic
  headers for runtime catalog pages.

## Route Policy

Prerendered/static in the staging SSR build:

- `/`
- service pages and service landing pages
- blog, legal, cart, checkout, success, contact, and static content shells

Runtime SSR in the staging build:

- `/catalog/`
- `/catalog/?...` query pages
- `/brands/`
- `/brands/[slug]`
- `/product/[slug]`
- configured catalog SEO pages under `/catalog/[virtual]`

This remains staging-only. The public static build still uses
`web/astro.config.mjs` and prerenders product, brand detail, and virtual catalog
routes until a production cutover is explicitly approved.

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

The smoke checks `GET /api/v1/catalog/revision`, requires
`X-Catalog-Revision` and `X-Web-Data-Cache` on runtime pages, compares catalog
and product prices/titles against the API fixture, verifies a brand page and
brand count, and checks one static `/_astro` asset.

If the API catalog lookup should not choose the product or brand automatically,
set:

```bash
SSR_SMOKE_PRODUCT_PATH=/product/<known-slug>/ npm run smoke:ssr:staging
SSR_SMOKE_BRAND_PATH=/brands/<known-brand>/ npm run smoke:ssr:staging
```

After manual Manager/API edits, use these read-only assertions as freshness
evidence:

```bash
# Price change: API product price must match staging product and catalog HTML.
SSR_SMOKE_PRODUCT_PATH=/product/<edited-slug>/ \
SSR_SMOKE_EXPECT_CATALOG_PRODUCT_PATH=/product/<edited-slug>/ \
npm run smoke:ssr:staging

# Unpublish/delete: product detail must return 404 and disappear from /catalog/.
SSR_SMOKE_UNPUBLISHED_PRODUCT_PATH=/product/<unpublished-slug>/ \
npm run smoke:ssr:staging

# New product: product detail must render and /catalog/ must include its link.
SSR_SMOKE_PRODUCT_PATH=/product/<new-slug>/ \
SSR_SMOKE_EXPECT_CATALOG_PRODUCT_PATH=/product/<new-slug>/ \
npm run smoke:ssr:staging

# Brand count/list change: choose the affected brand instead of the default.
SSR_SMOKE_BRAND_PATH=/brands/<brand-slug>/ npm run smoke:ssr:staging
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

- `/catalog/`, query catalog pages, `/brands/`, `/brands/[slug]`,
  `/product/[slug]`, and configured `/catalog/[virtual]` pages fetch from the
  API at request time in the staging Node runtime.
- Each runtime request first reads `GET /api/v1/catalog/revision`.
- GET API responses used by those pages are cached in-process by
  `catalog_revision + URL` for a short runtime TTL.
- If the revision endpoint is unavailable, the runtime uses a short fallback
  cache bucket and emits `X-Web-Data-Cache: stale`.
- Runtime pages emit `X-Catalog-Revision`, `X-Web-Data-Cache: hit|miss|stale`,
  and `Cache-Control: no-store`.
- Missing/unpublished product, brand, or virtual catalog slugs return 404 from
  the runtime instead of redirecting to a stale static shell.

Follow-up freshness work to investigate:

- Explicit invalidation trigger from manager after price, availability,
  publication, or product-list updates.
- Production Cloudflare/nginx cache policy for runtime HTML after staging
  evidence is accepted.

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
