# Storefront service extraction

## Goal

Move the Astro + Vue storefront from `web/` into the private `mvnby/mvn-web`
repository without interrupting `mvn.by`, catalog publication, or the VPS
fallback. The storefront must remain an API consumer and must never gain direct
database access.

## Service boundary

The future repository owns:

- all files currently under `web/`;
- storefront tests, builds, static and SSR images;
- Cloudflare Pages and web VPS deployment workflows;
- public smoke checks and storefront rollback tooling.

The API repository continues to own:

- product, catalog, filter, configuration, and revision APIs;
- catalog mutation and publication state;
- manager workflows and authentication;
- the rebuild status endpoint and callback verification.

The only runtime connection is HTTP through `INTERNAL_API_URL` and
`PUBLIC_API_URL`. A storefront build may receive the immutable API-compatible
web commit SHA and a catalog revision, but it must not receive database or bot
credentials.

## Current coupling to remove

1. Web deployment workflows and release scripts live in the API repository.
2. `SystemService` dispatches `rebuild-web.yml` in the API repository.
3. The web rebuild callback and deployment secrets are configured for that
   workflow location.
4. Root Docker Compose files still describe the storefront runtime.

The local `web` scripts are now self-contained and `npm run audit:boundary`
prevents source imports, package scripts, and sensitive runtime configuration
from crossing back into the monolith.

## Phased migration

### 1. Establish the boundary

- Keep all storefront checks runnable from inside `web/`.
- Run the boundary audit in monolith CI.
- Document API-only ownership and the current deployment coupling.

No traffic or production configuration changes in this phase.

### 2. Create and synchronize `mvnby/mvn-web`

- Import `web/` with its Git history where practical.
- Add standalone CI, dependency updates, and branch protection.
- Copy web deploy and rollback scripts into the new repository.
- Build the same monolith commit and new-repository commit and compare route
  inventory, release metadata, and smoke results.

The monolith remains the production source during comparison.

### 3. Decouple catalog rebuild dispatch

- Configure the API with explicit web repository owner, name, workflow, and
  branch settings.
- Dispatch the new repository with `catalog_revision` through a GitHub App or a
  narrowly scoped fine-grained token.
- Preserve the signed callback to `/api/system/rebuild-web/complete`.
- Prove success, failure, retry, and duplicate-dispatch behavior.

### 4. Shadow deployment

- Deploy `mvn-web` to a separate Cloudflare preview and SSR shadow runtime.
- Compare catalog totals, canonical URLs, sitemaps, key product pages, asset
  hashes, and release SHA with the existing production pipeline.
- Run load and rollback drills before any traffic change.

### 5. Cut over and clean up

- Switch the production web deployment source to `mvn-web` while retaining the
  existing atomic VPS release as rollback.
- Observe at least one normal catalog rebuild and one controlled rollback.
- Remove `web/`, web-only workflows, scripts, and Compose services from the API
  repository only after both paths are proven.

## Rollback rule

Until the final cleanup, rollback means selecting the last known-good atomic VPS
release or Cloudflare Pages deployment. Do not repair a bad storefront release
by changing API data or granting the storefront direct database access.
