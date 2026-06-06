# Production Web Runtime Freshness Runbook

Related issue: #471

This is the production design and runbook for moving the storefront from a
static-only freshness model to a hybrid runtime model on the new web VPS. It is
intentionally a design/runbook step: it does not switch public `mvn.by` to SSR,
does not remove the static deploy path, and does not change Cloudflare, nginx,
DNS, or VPS state by itself.

## Current State

Public production:

- `mvn.by` and `www.mvn.by` are proxied through Cloudflare to the new web VPS
  `153.80.244.78`.
- nginx serves the public static Astro build from `/var/www/mvn.by/current`.
- The legacy `mvn-web` host at `178.159.240.174` remains the static storefront
  reserve/fallback target.
- API traffic stays separate at `https://api.mvn.by`.

Current GitHub web deploy:

- `.github/workflows/deploy.yml` still builds `web/dist/` in GitHub Actions when
  storefront-relevant files change, then rsyncs the static bundle to
  `SSH_HOST_WEB` / `SSH_WEB_TARGET`.
- `.github/workflows/rebuild-web.yml` is the manual static rebuild path. It also
  builds `web/dist/` in GitHub Actions and rsyncs it to the web host.
- Both web build paths use `INTERNAL_API_URL` at build time and `PUBLIC_API_URL`
  for browser API calls.
- This means manager/API catalog changes do not update prerendered HTML until a
  static rebuild is run.

Staging runtime already proven by #464 / PR #469 and extended by #476:

- `web/astro.config.ssr.mjs` is a separate Astro Node standalone config with
  `output: "server"` and staging base `/__ssr-staging`.
- `docker-compose.web.yml` runs `web-ssr-staging` bound to
  `127.0.0.1:4321`.
- `ssr-staging.mvn.by` is protected with basic auth, sends noindex/no-store,
  and does not affect the public static root.
- Manager audit confirmed authenticated staging smoke through Cloudflare and
  public static production remained healthy.
- High-freshness staging pages use `GET /api/v1/catalog/revision` as a
  revision key for a short in-process data cache and emit
  `X-Catalog-Revision` plus `X-Web-Data-Cache: hit|miss|stale`.

Current storefront data patterns:

- `web/astro.config.mjs` is still static production output.
- Services, blog, legal pages, contact/cart/checkout/success, and the home page
  remain prerendered/static in the SSR staging build.
- `/catalog/`, `/catalog/?...`, `/brands/`, `/brands/[slug]`,
  `/product/[slug]`, and configured `/catalog/[virtual]` pages are request-time
  SSR surfaces in staging.
- `web/src/utils/api.js` uses `import.meta.env.SSR` for both SSG/build-time and
  server/runtime contexts, but the staging runtime freshness path is explicitly
  gated by `SSR_RUNTIME_FRESHNESS=true`; production runtime work must keep this
  split between strict `getStaticPaths()` behavior and softer request-time fetch
  behavior.
- Public API reads already filter published catalog data through
  `ProductReadService` / `ProductDAO` with `is_published=True`.
- Product and catalog-affecting writes currently flow through multiple paths:
  manager product edits, bulk price operations, product delete, brand edits,
  imports, supplier mappings, local stock updates, and supplier sync.

## Target Options

### Option A: VPS-hosted static build triggered by GitHub

GitHub sends a bounded command to the web VPS. The VPS fetches a requested SHA,
runs the static build locally, and flips `/var/www/mvn.by/current` to the new
release after smoke checks.

Use this for code deploy reliability if GitHub-hosted rsync remains flaky.
Do not treat it as the primary freshness answer: a wrong price, unpublished
product, or new product would still need a static build unless another
invalidation path exists.

### Option B: Astro Node runtime with selected prerendered routes

Cloudflare routes public traffic to nginx on the web VPS. nginx serves immutable
assets directly and proxies high-freshness HTML requests to an Astro Node
runtime on localhost. In Astro `output: "server"` mode, static pages opt into
`export const prerender = true`.

Recommended for production after staging validation. It gives full SEO HTML for
runtime pages without making blog/legal/service shells depend on live catalog
fetches.

Recommended initial runtime route policy:

| Route group | Production mode after approval | Freshness goal |
| --- | --- | --- |
| `/_astro/*` | static file, immutable | code deploy only |
| `/media/*` local originals | static/proxy file | hours to days unless path changes |
| R2/generated media variants | CDN immutable URL | content-addressed, long cache |
| `/`, services, blog, legal, contact shells | prerender/static | code/content deploy or manual purge |
| `/catalog/` base | runtime SSR with short edge TTL/purge | new products, price, availability, publication |
| `/catalog/?...` query pages | runtime SSR, noindex, bypass or very short TTL | filters reflect API quickly |
| `/catalog/[virtual]` SEO pages | prerender at first, then runtime or purge-backed cache if stale prices matter | popular landing pages stay fast |
| `/brands/` | runtime SSR with short TTL/purge | brand list/count freshness |
| `/brands/[slug]` | runtime SSR or purge-backed cache | brand product membership freshness |
| `/product/[slug]` | runtime SSR with short TTL/purge | price, availability, publication state, JSON-LD |
| cart, checkout, form POSTs, manager, API | no edge HTML caching | correctness and privacy |

### Option C: Static prerender plus on-demand rebuild/invalidation

Keep production static but add a manager/API trigger that starts a static rebuild
or a narrowed page regeneration job.

This is useful as fallback and for controlled SEO landing page refreshes. It is
not the preferred primary model because the current Astro app does not have a
native page-level ISR pipeline, and full static builds still make urgent catalog
fixes depend on deploy/rebuild latency.

### Option D: TTL/SWR caches for high-freshness data

Use short Cloudflare/nginx/runtime TTLs to reduce API load and keep pages fast.
This must be conservative for price and publication state. Cloudflare can serve
expired content during `stale-while-revalidate` when origin headers allow it,
so corrected bad prices should rely on explicit purge plus short TTL, not long
SWR windows.

Recommended first HTML policy:

- Runtime HTML with prices/publication state: start with bypass or
  `max-age=30, stale-while-revalidate=30` only after staging proves purge.
- Do not add `stale-if-error` to product/catalog HTML while publication state is
  a correctness requirement.
- Avoid nginx microcaching for HTML in the first cutover; keep the first cache
  layer Cloudflare plus the Astro data cache.
- Keep immutable assets long-lived and content-addressed.

Relevant references:

- Cloudflare revalidation and SWR:
  <https://developers.cloudflare.com/cache/concepts/revalidation/>
- Cloudflare cache-control behavior:
  <https://developers.cloudflare.com/cache/concepts/cache-control/>
- Cloudflare purge options:
  <https://developers.cloudflare.com/cache/how-to/purge-cache/>
- Astro on-demand rendering:
  <https://docs.astro.build/en/guides/on-demand-rendering/>
- Astro `prerender` routing:
  <https://docs.astro.build/en/reference/routing-reference/#prerender>

### Option E: Manager/API revision and purge signal

Add an API-side catalog revision and invalidation service. This is the missing
piece that lets runtime SSR and Cloudflare cache cooperate.

Recommended contract:

- Public read endpoint: `GET /api/v1/catalog/revision`
  - response: `revision`, `updated_at`, and optional `scopes`;
  - no authentication;
  - cheap DB read from a `GlobalConfig` key or dedicated table.
- Internal service: `CatalogRevisionService.bump(scope, product_ids, slugs)`.
- Writer hooks after successful commit:
  - manager product patch/delete;
  - bulk price operations;
  - brand create/update/delete;
  - tag/spec/category membership edits;
  - importer create/update paths;
  - supplier mapping/local stock changes;
  - supplier sync when offer qty/RRC changes mapped products.
- Web runtime data cache key:
  - route/query plus `catalog_revision`;
  - short TTL fallback if the revision endpoint is temporarily unavailable.
- Cloudflare purge:
  - exact URLs first;
  - prefix purge for `/catalog` and `/brands` when many products change;
  - cache tags later if adopted consistently in origin headers.

Cloudflare supports URL, hostname, tag, prefix, and purge-everything APIs.
Exact URL purge is the safest first implementation. Prefix and tag purges are
useful for bulk catalog changes but should be rate-limited and observed.

## Recommendation

Use a hybrid production model after owner approval:

1. Keep the existing static production deploy and `mvn-web` fallback intact.
2. Keep `ssr-staging.mvn.by` as the validation surface.
3. Add catalog revision and writer-side invalidation in the API.
4. Promote Astro Node runtime only for high-freshness SEO/catalog pages:
   product detail, catalog, brand list, brand detail, and optionally virtual
   catalog landing pages.
5. Keep static/prerendered pages for home, services, blog, legal, contact, and
   other content shells.
6. Let Cloudflare cache immutable assets aggressively and cache high-freshness
   HTML only with short TTL plus explicit purge.
7. Make routine manager catalog changes trigger revision/purge, not GitHub
   static builds.

Target topology after cutover approval:

```text
Cloudflare proxied mvn.by
  -> nginx on 153.80.244.78
      -> serve /_astro/* from current runtime client assets
      -> serve static rollback release when rollback is enabled
      -> proxy high-freshness HTML to Astro Node on 127.0.0.1:4322

Astro Node web-public
  -> api.mvn.by/api/v1 or later private inter-VPS API path
  -> in-process data cache keyed by route/query/catalog revision

Manager/API writes
  -> commit DB change
  -> bump catalog revision
  -> purge Cloudflare URLs/prefixes/tags for affected public routes
```

## High-Freshness Data Policy

Prices:

- Source of truth: API product rows and manager/import/bulk price writers.
- Product detail HTML, JSON-LD, catalog cards, brand cards, and structured
  product snippets must not show corrected bad prices after purge.
- Target stale window: immediate after purge, otherwise no more than 30-60
  seconds during the first production runtime phase.
- Purge paths: `/product/<slug>/`, `/catalog/`, affected brand page,
  relevant virtual catalog pages, and cached query/list routes when known.

Availability:

- Source of truth: local stock, supplier mappings/offers, supplier sync, and
  `ProductSupplyMetricsService` derived `availability_status`.
- Product/detail/list HTML must reflect in-stock, 2-3 day, check availability,
  and out-of-stock changes quickly.
- Target stale window: same as prices.
- Bulk supplier sync can affect many products; prefer prefix purge for catalog
  and brand pages plus exact product URL purge for known mapped products.

Publication state:

- Source of truth: `Product.is_published` and brand publication state.
- Requirement: unpublished products must not leak through public detail routes,
  list pages, brand pages, or cached HTML.
- Target stale window: immediate after purge; fallback TTL should be minimal.
- Runtime product route must return 404 for unpublished/deleted products and
  must avoid stale-if-error for this route group.

Product existence and list membership:

- New published products should appear in `/catalog/`, relevant brand pages, and
  product detail URLs without a full static rebuild.
- Deleted/unpublished products should disappear from lists and return 404 on
  detail pages after purge.
- Brand/category/tag changes bump the same catalog revision because they change
  public list membership.

Brand/category catalog lists:

- `/brands/`, `/brands/<slug>/`, `/catalog/`, and `/catalog/[virtual]` depend on
  published brand/product/tag membership.
- Target stale window: 60 seconds after routine edits, immediate after explicit
  purge for urgent changes.
- Brand edits should purge `/brands/`, the brand detail URL, `/catalog/`, and
  any product detail pages whose visible brand/title data changed.

## Cloudflare And Nginx Cache Policy

Cloudflare cache rules:

| Route group | Cloudflare behavior | Origin/cache headers |
| --- | --- | --- |
| `/_astro/*` | cache aggressively | `public, max-age=31536000, immutable` |
| R2 variant CDN URLs | cache aggressively | `public, max-age=31536000, immutable` |
| local `/media/*` originals | cache, shorter TTL | hours to days unless URLs become content-addressed |
| `/`, services, blog, legal static HTML | cache with moderate TTL | 10-30 min, purge on code/content deploy |
| `/product/*` | bypass or 30-60 sec TTL at first | no `stale-if-error`; purge exact URL on writes |
| `/catalog/` base | bypass or 30-60 sec TTL | purge on catalog revision bump |
| `/catalog/?*` | bypass or very short TTL, include query in cache key if cached | `noindex,follow` |
| `/catalog/*` virtual pages | short TTL or purge-backed cache | purge for price/publication/list changes |
| `/brands/`, `/brands/*` | short TTL or purge-backed cache | purge on brand/catalog changes |
| `/cart`, `/checkout`, lead/order POSTs | bypass/no-store | private/no-store if server state is added |
| `/api/*`, `/api/manager/*` | bypass Cloudflare cache | API correctness/privacy |

Cloudflare purge strategy:

- Use exact URL purge first for product and brand pages.
- Use prefix purge for broad list changes:
  - `mvn.by/catalog`
  - `mvn.by/brands`
- Add `Cache-Tag` headers later if the team wants more selective purges:
  - `catalog`
  - `product:<id>`
  - `brand:<slug>`
  - `category:<slug>`
- Do not use purge-everything for normal manager writes.
- Rate-limit bulk purge calls and coalesce changes from imports/supplier sync.

Backend purge env contract:

- `CLOUDFLARE_PURGE_ENABLED=false` by default.
- `CLOUDFLARE_PURGE_DRY_RUN=true` by default.
- `CLOUDFLARE_ZONE_ID` for the `mvn.by` zone.
- `CLOUDFLARE_API_TOKEN` with cache purge permission only.
- `PUBLIC_SITE_URL=https://mvn.by` for exact storefront URL generation.

Nginx policy:

- Do not enable nginx HTML caching in the first public runtime cutover.
- Serve `/_astro/*` directly from the current runtime client asset directory.
- Proxy high-freshness HTML to the Astro container and preserve
  `Cache-Control`, `ETag`, `Last-Modified`, `X-Catalog-Revision`, and
  diagnostic cache headers.
- Keep a static-only nginx config or snippet ready for rollback.
- Keep staging `ssr-staging.mvn.by` noindex/no-store.

Bad corrected price rule:

- A manager price fix must call revision bump and Cloudflare purge.
- Product/catalog/brand HTML should then MISS or revalidate at Cloudflare and
  fetch fresh API data.
- If purge fails, the short TTL is the backup. During first cutover keep that
  TTL small enough that a bad price cannot sit at the edge for long.

## Migration Phases

### Phase 0: Design only

- Keep public production static.
- Keep `.github/workflows/deploy.yml` and `.github/workflows/rebuild-web.yml`
  static behavior.
- Keep `web-ssr-staging` as staging only.
- Land this runbook and read-only smoke tooling.

### Phase 1: Staging freshness implementation

Implement on staging only:

- API catalog revision endpoint.
- Writer-side revision bump hooks for product, brand, import, supplier, and
  bulk price paths.
- Astro runtime route changes for product detail, catalog, brands, and selected
  virtual catalog pages.
- Cache headers and diagnostic headers:
  - `Cache-Control`
  - `X-Catalog-Revision`
  - optional `X-Web-Data-Cache: hit|miss|stale`
- Cloudflare purge dry-run/logging first, then live purge for staging host.

Staging validation:

- Price change for a test product.
- Publish/unpublish for a test product.
- New product visibility.
- Brand list/count update.
- Supplier/local stock availability update.
- Confirm staging Cloudflare/proxy cache does not preserve stale HTML after
  purge or after the fallback TTL.

### Phase 2: Production shadow

Do not route public apex/root traffic yet.

- Use `docs/web-public-shadow-runtime-runbook.md` for the concrete shadow
  workflow.
- Run `web-public-shadow` on the web VPS bound to `127.0.0.1:4322`.
- Build from `/opt/air-api` at a recorded commit SHA.
- Expose only a protected/noindex shadow hostname or origin-only host header
  route.
- Run the same route and freshness smoke checks against shadow.
- Verify Cloudflare cache rules in simulation or on the protected hostname.

### Phase 3: Public cutover

Requires explicit owner approval.

- Save current nginx config and static release path.
- Build/start `web-public` runtime on the web VPS.
- Run localhost smoke against `127.0.0.1:4322`.
- Install nginx public runtime config:
  - static assets served directly;
  - high-freshness HTML proxied to Astro;
  - static fallback root still present on disk.
- Apply Cloudflare cache rules.
- Purge affected HTML once.
- Run public smoke:
  - `/`
  - `/catalog/`
  - `/brands/`
  - one brand page
  - one product page
  - one `/_astro/*` asset
  - `https://api.mvn.by/api/health`
- Run freshness smoke for price, publication, and new product before declaring
  the cutover successful.

### Phase 4: Rollback

Fast same-VPS rollback:

1. Restore the static-only nginx config or switch the public server block back
   to `/var/www/mvn.by/current`.
2. `nginx -t && systemctl reload nginx`.
3. Stop only the runtime service:
   `docker compose -f /opt/air-api/docker-compose.web.yml stop web-public`.
4. Purge Cloudflare HTML for `mvn.by`.
5. Run public static smoke.

Reserve host rollback:

1. Restore Cloudflare `mvn.by` and `www.mvn.by` A records to
   `178.159.240.174` if the new web VPS itself is unhealthy.
2. Restore legacy static deploy secrets if needed.
3. Run the manual static rebuild workflow.
4. Smoke public routes after DNS/proxy propagation.

## Operational Shape

GitHub responsibilities:

- Keep current backend Docker image build/deploy.
- Keep current static web build/rsync workflows for rollback.
- After owner approval, add a separate manual `deploy-web-runtime` workflow.
- The shadow runtime workflow sends a bounded command to the web VPS rather than
  rsyncing `web/dist/`:
  - `cd /opt/air-api`
  - `git fetch origin <sha>`
  - `git checkout --detach <sha>`
  - `docker compose -f docker-compose.web.yml build web-public-shadow`
  - `docker compose -f docker-compose.web.yml up -d --no-deps web-public-shadow`
  - run localhost smoke
  - reload nginx only in the promotion step
- A later hardening step may build and push a GHCR web image in GitHub and make
  the VPS pull by digest. That improves reproducibility but is not required for
  the first runtime cutover.

Web VPS `/opt/air-api` responsibilities:

- Repo checkout for runtime build commands.
- `docker-compose.web.yml` with staging service and `web-public-shadow` service.
- `.env.web-runtime` or shell env with:
  - `INTERNAL_API_URL`
  - `PUBLIC_API_URL`
  - `PUBLIC_SITE_URL`
  - `PUBLIC_GTM_ID`
  - runtime port/base path
- No Cloudflare API token is required on the web VPS if purge is API-side.
- nginx snippets/site configs for:
  - current static production;
  - staging SSR hostname;
  - future public runtime;
  - rollback static-only mode.
- Static releases retained under `/var/www/mvn.by/releases`.

API/backend responsibilities:

- Store Cloudflare purge credentials on the API host only:
  - `CLOUDFLARE_ZONE_ID`
  - `CLOUDFLARE_API_TOKEN` with least privilege for cache purge
- Store optional web revalidate secret only if an internal web endpoint is used.
- Bump catalog revision after committed catalog-affecting writes.
- Queue/coalesce purge jobs for imports and supplier sync.
- Log purge success/failure without secrets.

Secrets policy:

- Do not commit Cloudflare tokens, basic-auth passwords, or `.env.web-runtime`.
- Do not print secrets in Actions, issue comments, PRs, or chat.
- Cloudflare DNS and purge actions should be scoped to the `mvn.by` zone.

## Verification Plan

Read-only public route smoke:

```bash
bash scripts/smoke_web_public.sh
```

Useful overrides:

```bash
BASE_URL=https://ssr-staging.mvn.by \
API_ORIGIN_URL=https://api.mvn.by \
BASIC_AUTH='<user>:<password>' \
PRODUCT_PATH=/product/<slug>/ \
BRAND_PATH=/brands/<slug>/ \
bash scripts/smoke_web_public.sh
```

Freshness smoke:

1. Pick a safe test product and record current API/product page values.
2. Change price in Manager.
3. Confirm API `GET /api/v1/products/<slug-or-id>` returns the new price.
4. Confirm product detail HTML, JSON-LD, catalog page, and brand page show the
   new price after purge or within fallback TTL.
5. Publish a new test product.
6. Confirm `/catalog/`, the brand page, and `/product/<slug>/` show it.
7. Unpublish the test product.
8. Confirm public product API returns 404, product page returns 404, and
   catalog/brand lists no longer include it.
9. Change local stock or supplier availability and confirm availability labels
   update on product/detail/list routes.
10. Check `CF-Cache-Status`, `Cache-Control`, and `X-Catalog-Revision` headers
    for product/catalog/brand HTML.

Deploy failure rollback smoke:

```bash
bash scripts/smoke_web_public.sh
curl -fsS https://api.mvn.by/api/health
```

Required public smoke paths:

- `/`
- `/catalog/`
- `/brands/`
- one brand page
- one product page
- one `/_astro/*` asset
- `https://api.mvn.by/api/health`
- `https://api.mvn.by/api/v1/products?limit=5`
- `https://api.mvn.by/api/v1/filters/config`

## Decision Gates

Still owner/manager gated:

- Whether product detail initial HTML must become runtime SSR in the first
  production cutover, or whether a short transitional client refresh is
  acceptable.
- Exact acceptable stale window for prices and publication state.
- Whether Cloudflare HTML cache starts as bypass or 30-60 second TTL.
- Whether to use exact URL purge only, or introduce prefix/tag purges in the
  first implementation.
- Whether runtime uses public `https://api.mvn.by/api/v1` first or waits for a
  private inter-VPS API path.
- Whether code deploy builds on the VPS first or pushes a GHCR web image.
- Whether Cloudflare R2 product media variant rollout is done before, during, or
  after runtime cutover.
- Whether Cloudflare Load Balancing is purchased/enabled now or left as a later
  failover project.

Cloudflare Load Balancing note:

- The first safe failover shape remains manual DNS/proxy rollback to the static
  reserve or static same-VPS nginx config.
- Cloudflare Load Balancing can later add active health checks and origin
  failover, but it should not be a mandatory dependency for the first runtime
  cutover.
- Reference: <https://developers.cloudflare.com/load-balancing/>

## Risks

- Product detail SSR increases runtime API dependency for a high-traffic SEO
  route. Mitigate with short data caches, fast API health checks, and static
  rollback.
- Cloudflare SWR can serve stale HTML during revalidation. Keep SWR windows
  short for price/publication routes and require purge for urgent corrections.
- Purge jobs can fail or hit rate limits. Coalesce bulk changes and keep TTL as
  backup.
- Current product writes are spread across manager, importer, brand, supplier,
  and DAO/service paths. A revision bump added to only one endpoint will miss
  changes.
- In-process Astro data caches can outlive Cloudflare purge unless they are
  keyed by catalog revision or explicitly invalidated.
- Publication-state bugs are higher severity than price-delay bugs because
  unpublished products must not leak through cached HTML.
- R2 media variants are safe to cache long-term only because their URLs are
  content-addressed. Local product originals should stay on a shorter cache
  policy until fully versioned.
