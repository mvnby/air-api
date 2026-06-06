# Astro SSR And Runtime VPS Migration Plan

Related issue: #461

Issue #464 staging spike implementation now lives in
[`docs/astro-ssr-staging-runbook.md`](astro-ssr-staging-runbook.md). The
production recommendation remains unchanged: keep public `mvn.by` static until
the staging runtime, cache behavior, and rollback path are proven.

Issue #471 production runtime freshness design now lives in
[`docs/web-runtime-freshness-runbook.md`](web-runtime-freshness-runbook.md).
Use that runbook for Cloudflare cache rules, catalog revision/invalidation,
runtime route policy, migration phases, and rollback gates.

This is a planning document for using the new web VPS capabilities safely. It
does not change production, Cloudflare, DNS, VPS state, secrets, or env.

## Current Storefront Shape

The storefront is currently an Astro static build:

- `web/astro.config.mjs` has `output: 'static'`.
- `@astrojs/node` is already installed in `web/package.json`, but the adapter is
  not wired into Astro config.
- GitHub `deploy-frontend` and manual `rebuild-web` both build `web/dist/` and
  rsync it to `SSH_HOST_WEB`.
- The new web VPS target in docs is `mvn`, IP `153.80.244.78`, path
  `/var/www/mvn.by/current`.
- API remains separate on `api.mvn.by`.
- The web build uses `INTERNAL_API_URL` during static generation and
  `PUBLIC_API_URL` for browser-side API calls.

Current route patterns:

| Surface | Current behavior | Notes for SSR |
| --- | --- | --- |
| `/`, `/montaj-konditionerov` | Static page, fetches install pricing via `getInstallationPricingInfo()` at build time. | Could remain prerendered; dynamic pricing is already refreshed in client components where needed. |
| `/catalog` | Static page generated once; reads `Astro.url.searchParams`, but static deploy only has the no-query HTML. Client `CatalogApp` fetches filtered results after hydration. | Good candidate for SSR if server-rendered filtered HTML becomes important. |
| `/catalog/[virtual]` | `getStaticPaths()` from local `VIRTUAL_CATEGORIES`; fetches API catalog data at build time. | Keep prerendered for SEO landing pages unless availability/prices must be fresher in HTML. |
| `/product/[slug]` | `getStaticPaths()` fetches all products with strict SSG failure if API returns no products. | Keep all current product pages prerendered first, or switch the route to request-time SSR deliberately later. |
| `/brands` | Fetches public brands at build time. | Can stay prerendered or become low-cache SSR if brand catalog changes often. |
| `/brands/[slug]` | `getStaticPaths()` fetches brands; page fetches brand catalog data at build time. | Keep popular brand pages prerendered; SSR helps if brand/product counts change often. |
| `/blog/[...slug]`, `/blog`, content pages | Content collection/static local content. | Keep prerendered for SEO/performance. |
| `/services/[slug]` | `getStaticPaths()` fetches selected service pages with fallback list and redirects canonical service slugs. | Keep prerendered; current fallback behavior is intentionally robust. |
| `/cart`, `/checkout`, contact/lead forms | Static shell with client-side Vue posting to API. | SSR is not required for current UX; future personalization could use server routes. |

Important current assumptions:

- `web/src/utils/api.js` uses `import.meta.env.SSR` to choose
  `INTERNAL_API_URL` for server/build contexts and `PUBLIC_API_URL` for browser
  contexts. In Astro, static generation also runs in the server context, so many
  comments that say "SSR" actually describe SSG/build-time fetches today.
- `getProducts()` is strict when `import.meta.env.SSR` is true. That protects
  static product route generation, but in full server mode it may be too strict
  for request-time fallback if reused outside `getStaticPaths()`.
- `web/Dockerfile.prod` already expects an Astro Node server entrypoint at
  `./dist/server/entry.mjs`, but current static output does not produce that
  file. Treat this as a dormant/incomplete runtime artifact until the adapter is
  actually wired.

## Recommendation

Do not switch the whole site to SSR immediately.

Recommended path:

1. Keep production static for now.
2. Add a staging/spike implementation that runs Astro Node server output on the
   new web VPS on an alternate port or staging hostname while static production
   remains available.
3. Keep SEO/content-heavy routes prerendered.
4. Move only the surfaces that genuinely benefit from request-time data to SSR:
   catalog query pages first, then selected brand/product list surfaces if the
   owner accepts the runtime complexity.
5. Promote SSR only after deploy, cache, smoke, rollback, and observability are
   rehearsed.

This fits the current codebase because the storefront already has a strong SSG
SEO path, client-side catalog interactivity, and API-based fresh price/stock
refresh in product/cart components. The new VPS gives us the option to run a
Node server, but it does not force us to trade away the static rollback path.

## Option 1: Low-Risk Hybrid, Static Production First

Topology:

```text
Cloudflare/mvn.by -> nginx on web VPS -> static /var/www/mvn.by/current
Browser JS -> https://api.mvn.by/api/v1
Build-time SSG -> INTERNAL_API_URL -> API tunnel or production API
```

What changes now:

- Documentation and deployment terminology only.
- Keep `web/astro.config.mjs` as `output: 'static'`.
- Keep `deploy-frontend` and `rebuild-web` rsyncing `web/dist/`.
- Add future runtime spike behind a staging hostname, alternate port, or separate
  nginx location without changing public `mvn.by`.

What stays prerendered/static:

- Blog and MDX content.
- Static legal/contact/service pages.
- `/catalog/[virtual]` SEO landing pages.
- `/product/[slug]` and `/brands/[slug]` for now.
- `/`, unless the owner needs install pricing in HTML to update without rebuild.

Where runtime can be added later:

- Astro server routes for experiments under `/runtime/*` or a staging hostname.
- A dynamic catalog endpoint/page that renders query-filtered first HTML.
- Future recommendations/personalization surfaces that should not be generated
  for every possible query at build time.

Pros:

- Lowest risk and fastest rollback.
- No new always-on Node process required for production.
- Preserves current SEO behavior and static performance.
- Lets the team validate SSR on the new VPS without coupling it to production
  launch.

Cons:

- Product, brand, service, and install-pricing HTML can remain stale until the
  next rebuild.
- Filtered `/catalog?...` pages still rely on hydrated client fetching rather
  than server-rendered filtered HTML.
- Does not exercise the dormant `web/Dockerfile.prod` server entrypoint.

Recommended first implementation PR after this plan:

- Keep static production.
- Add a separate SSR spike branch/config or staging-only workflow that can build
  Astro server output and run it on `mvn` behind a non-public/staging route.
- Add smoke checks for the staging runtime before touching production routing.

## Option 2: Astro Node SSR On VPS With Selected Prerender

Target topology:

```text
Cloudflare/mvn.by
  -> nginx on web VPS
      -> serve immutable assets from Astro dist/client directly
      -> proxy page requests to Astro Node server on 127.0.0.1:4321

Astro Node server -> https://api.mvn.by/api/v1 or owner-approved private API path
Browser JS        -> https://api.mvn.by/api/v1
```

Astro config direction:

```js
import node from '@astrojs/node';

export default defineConfig({
  site: 'https://mvn.by',
  integrations: [vue(), mdx(), tailwind(), sitemap()],
  output: 'server',
  adapter: node({ mode: 'standalone' }),
});
```

Route rendering policy:

- Set `export const prerender = true` on routes that should stay static:
  - `/blog/[...slug].astro` and blog index.
  - legal/static pages: `/privacy`, `/terms`, `/offer`, `/contacts`,
    `/success`, `/404`.
  - static service pages and local content pages.
  - `/catalog/[virtual]` SEO landing pages.
  - `/product/[slug]` and `/brands/[slug]` only if the future implementation
    keeps those dynamic routes fully prerendered.
- Let request-time SSR handle:
  - `/catalog` with query params.
  - brand pages if product counts/list freshness matters more than static cache.
  - product pages if price/availability in initial HTML must be fresh.
  - future recommendations, personalization, lead prefill, or server-side A/B
    tests.

Nginx direction:

```nginx
server {
    listen 80;
    server_name mvn.by www.mvn.by;

    root /var/www/mvn.by/current/client;

    location /_astro/ {
        alias /var/www/mvn.by/current/client/_astro/;
        add_header Cache-Control "public, max-age=31536000, immutable";
        try_files $uri =404;
    }

    location /img/ {
        try_files $uri @astro;
        add_header Cache-Control "public, max-age=86400";
    }

    location / {
        try_files $uri @astro;
    }

    location @astro {
        proxy_pass http://127.0.0.1:4321;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Process model:

- Prefer Docker Compose for the first production-grade runtime because the repo
  already uses Docker Compose for the API and `web/Dockerfile.prod` exists.
- Keep systemd as the host-level supervisor for Docker itself, not for raw Node,
  unless the owner wants a simpler single-service VPS without Docker.
- Avoid PM2 unless there is an owner preference; it would introduce another
  process model that the repo does not use elsewhere.

Future compose sketch:

```yaml
services:
  web:
    build:
      context: ./web
      dockerfile: Dockerfile.prod
    restart: always
    environment:
      HOST: 0.0.0.0
      PORT: 4321
      INTERNAL_API_URL: https://api.mvn.by/api/v1
      PUBLIC_API_URL: https://api.mvn.by/api/v1
      PUBLIC_SITE_URL: https://mvn.by
    ports:
      - "127.0.0.1:4321:4321"
```

Deploy model:

- Build an SSR artifact or Docker image in GitHub Actions.
- Upload/pull it to the web VPS.
- Start the new container alongside the old static directory.
- Run local origin smoke against `127.0.0.1:4321`.
- Switch nginx to proxy dynamic requests only after smoke passes.
- Keep the previous static `current` directory and nginx static config ready for
  rollback.

Pros:

- Fresh server-rendered catalog/query/product/brand HTML is possible.
- Future personalization and server routes become straightforward.
- The new VPS capability is used directly.

Cons:

- Adds an always-on Node runtime and runtime API dependency to storefront
  availability.
- Needs new deploy, nginx, smoke, process, cache, and rollback work.
- Full server output changes `getStaticPaths()` semantics: routes not explicitly
  prerendered may need request-time data fetches and 404 handling.

## Option 3: Full SSR Immediately

This is not recommended.

Full SSR would put every page behind the Node server unless explicitly
prerendered later. That maximizes flexibility but creates avoidable risk:

- Blog/legal/service content would depend on a Node process despite being static.
- Runtime API failures could affect more first HTML paths than necessary.
- Cloudflare/nginx caching has to be correct from day one.
- Rollback pressure is higher because the public site would move all at once.

Use this only after a staging SSR runtime has been proven and the owner accepts
the operational model.

## Route And Code Change Inventory For Future SSR PR

`web/astro.config.mjs`:

- Add `@astrojs/node` adapter.
- Change `output` to `server` for the SSR build variant.
- Decide whether to keep a separate static config/script for rollback builds.

`web/package.json`:

- Add explicit scripts such as:
  - `build:static` for current static output.
  - `build:ssr` for server output.
  - `start:ssr` for `node ./dist/server/entry.mjs`.
- Keep `npm run build` pointing to the currently approved production mode until
  the owner approves switching production.
- Align the runtime Node version between GitHub Actions and `web/Dockerfile.prod`
  before relying on the Docker image in production.

`web/src/utils/api.js`:

- Rename/comment `import.meta.env.SSR` usage so it does not imply only
  request-time SSR; it also runs during SSG.
- Split strict SSG route generation fetches from request-time runtime fetches.
- Add clear runtime fallback behavior for product/brand 404s and API errors.
- Consider request-local caching instead of module-level promises for values
  that should update without a process restart.

`web/src/pages/product/[slug].astro`:

- Current `getStaticPaths()` fetches all products and passes product props.
- In server output, decide between:
  - `prerender = true` for all/current product paths, preserving SSG behavior;
  - full request-time fetch by `Astro.params.slug` with cache headers and
    robust 404 handling.
- If the team wants popular products prerendered but long-tail products served
  by SSR, design that explicitly as a separate routing/cache strategy rather
  than assuming the current dynamic route will do both automatically.

`web/src/pages/brands/[slug].astro`:

- Same decision as products: prerender all known brands or fetch by slug at
  request time.
- Product list and count freshness may justify SSR before product detail pages.

`web/src/pages/brands/index.astro`:

- Currently build-time brand list. It can stay prerendered with rebuilds or move
  to low-cache SSR if brand publication changes often.

`web/src/pages/catalog.astro`:

- Best first SSR candidate. It already parses `Astro.url.searchParams`; in
  static mode that only affects build-time/no-query output, but in server mode
  it can render filtered first HTML.
- Add cache/noindex behavior for query pages deliberately.

`web/src/pages/catalog/[virtual].astro`:

- Keep prerendered unless the owner needs fresh availability in landing-page
  HTML. The route list is local config, so it is a clean static fit.

`web/src/pages/services/[slug].astro`:

- Current fallback list and canonical redirects are SSG-safe. Keep prerendered.
- If dynamic service pages expand beyond the hardcoded SEO slugs, revisit.

`web/src/pages/blog/[...slug].astro`:

- Keep prerendered. It uses local Astro content collections.

`web/src/components/ProductGroup.astro` and pages using it:

- Home page product groups are fetched during build today. In SSR they may fetch
  at request time unless the page is prerendered.
- Decide per page whether freshness justifies runtime dependency.

Vue client components:

- `CatalogApp.vue`, `PriceWithToggle.vue`, cart, checkout, contact forms, and
  availability leads already use browser-side API calls. SSR is optional for
  first HTML and should not replace client-side validation/submission.

## Caching Strategy

Cloudflare:

- Cache immutable assets under `/_astro/*` aggressively.
- Do not cache cart, checkout, form POSTs, or manager/API paths.
- For SSR HTML, start conservative:
  - product/brand/catalog base pages: short edge TTL or bypass until behavior is
    measured;
  - query catalog pages: noindex and either bypass or very short TTL;
  - prerendered blog/static pages: cache like static HTML.

Astro/nginx headers:

- `/_astro/*`: `Cache-Control: public, max-age=31536000, immutable`.
- Static images and files: owner-approved TTL, usually hours to days.
- SSR HTML with stock/price: `Cache-Control: public, s-maxage=60,
  stale-while-revalidate=300` only after verifying Cloudflare behavior.
- Lead/order/cart pages: `Cache-Control: no-store` if any personalized server
  state is added later.

API response caching:

- Keep backend API as source of truth.
- Consider API-side short cache for catalog/filter responses before relying on
  SSR under load.
- Avoid caching POST responses and availability lead/order creation.

## Smoke Checks And Monitoring

Static production checks that should remain:

```bash
curl -I https://mvn.by/
curl -I https://mvn.by/catalog/
curl -I https://www.mvn.by/
```

SSR staging/runtime checks for future implementation:

```bash
curl -fsS http://127.0.0.1:4321/
curl -fsS http://127.0.0.1:4321/catalog/
curl -fsS "http://127.0.0.1:4321/catalog?area_max=35&tag_slugs=cat-household"
curl -fsS http://127.0.0.1:4321/brands/
curl -fsS http://127.0.0.1:4321/product/<known-slug>
curl -I http://127.0.0.1:4321/_astro/<known-built-asset>.css
```

Public checks after promotion:

- `/`
- `/catalog/`
- one query catalog URL
- one known product URL
- `/brands/`
- one known brand URL
- `/cart/`
- `/checkout/`
- static assets under `/_astro/`

Monitoring signals:

- Node process/container running.
- Local port `127.0.0.1:4321` responds.
- nginx upstream errors and 5xx rate.
- API dependency failures from Astro server logs.
- RSS/memory restart count for the web process/container.
- Cloudflare cache status for assets and HTML.

## Rollback Plan

Static rollback must remain available through the first SSR rollout.

Fast rollback path:

1. Keep the last known-good static `web/dist/` deployed at a separate release
   path, for example `/var/www/mvn.by/static-rollback/<timestamp>`.
2. Keep the previous nginx static-only site config available.
3. If SSR runtime fails, switch nginx root back to the static release and remove
   or bypass the Astro upstream.
4. Reload nginx.
5. Stop the Astro Node container/process.
6. Run public static smoke checks.

DNS rollback should not be needed if SSR is introduced behind the same web VPS
nginx and the static release remains on disk.

GitHub rollback:

- Re-run the existing `rebuild-web.yml` static deploy workflow from `main` or
  the last known-good SHA.
- Ensure `SSH_HOST_WEB`, `SSH_USER_WEB`, and `SSH_WEB_TARGET` still point to the
  static target.

Data safety:

- SSR storefront must not write local state on the web VPS.
- Orders/leads continue to be written to `api.mvn.by`, so web rollback should
  not require DB changes.

## Future Implementation Checklist

1. Add explicit static and SSR build scripts.
2. Wire `@astrojs/node` adapter in an SSR branch/config.
3. Decide route-level `prerender` policy and add it deliberately.
4. Refactor `web/src/utils/api.js` comments and strict SSG/runtime behavior.
5. Add Docker Compose or systemd unit for Astro server; prefer Docker Compose
   unless owner chooses raw Node/systemd.
6. Add nginx config for direct asset serving plus reverse proxy to
   `127.0.0.1:4321`.
7. Add deploy workflow path for SSR artifact/image without removing static
   rebuild workflow.
8. Add runtime smoke checks and log capture.
9. Test on staging hostname or alternate port.
10. Document rollback and rehearse it before production promotion.

## Owner Decisions Still Needed

- Whether SSR should be staged on a subdomain, alternate port, or hidden nginx
  location first.
- Whether the web VPS should run Docker Compose, raw Node with systemd, or PM2.
- Whether `mvn.by` should keep Cloudflare caching HTML or initially bypass SSR
  HTML cache.
- Acceptable staleness for product price/stock in initial HTML.
- Which product/brand pages are SEO-critical enough to prerender.
- Whether runtime SSR may call `https://api.mvn.by` publicly or should use an
  owner-approved private inter-VPS path later.
- How long to keep static rollback releases on disk.
