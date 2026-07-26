# Storefront service extraction — completed

The public Astro + Vue storefront is owned by the private
[`mvnby/mvn-web`](https://github.com/mvnby/mvn-web) repository.

`mvnby/air-api` owns catalog data, public API contracts, orders, leads,
authentication and catalog-revision state. `mvn-web` owns storefront source,
tests, static/SSR builds, image tooling, release workflows and public smoke
checks. The services communicate only over HTTPS through `INTERNAL_API_URL`
and `PUBLIC_API_URL`; the storefront has no database access.

The API dispatches catalog-revision verification to `mvn-web` and accepts the
existing signed callback at `/api/system/rebuild-web/complete`. Production
storefront releases are built and deployed only from `mvn-web`; this repository
contains no fallback publisher or embedded storefront source.

For storefront development or operational procedures, use the documentation in
the `mvn-web` repository. API changes that affect public clients still require
backward-compatible HTTP contracts and an explicit storefront compatibility
check.
