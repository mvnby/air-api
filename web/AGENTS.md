# Storefront Service Guide

`web/` is an independently deployable Astro + Vue storefront. Keep it ready to
move to its own repository without copying backend implementation details.

## Boundary rules

- Communicate with MVN only through the documented HTTP API.
- Do not import files from the parent repository or read its database directly.
- Do not add backend, bot, database, storage, or OAuth secrets to this service.
- Keep build, test, audit, and runtime scripts inside `web/`.
- Treat `PUBLIC_API_URL` and `INTERNAL_API_URL` as the API boundary.

## Validation

Run from `web/`:

```bash
npm run audit:boundary
npm run audit:theme
npm run test:brands
npm run test:homepage
npm run test:catalog
npm run test:seo
npm run build
```

The build needs a reachable MVN API because the production storefront is
currently generated from live catalog data.
