# Catalog Decision Workspace

## Status

Accepted for the first read-only vertical slice.

## Decision

The Manager decision workspace is a separate server-side query projection,
not an extension of `ProductsView.vue` and not a post-pagination decoration by
`ProductSupplyMetricsService`.  Filters, active-supplier eligibility,
commercial aggregates, ordering, null semantics and the `Product.id` tie-break
are evaluated before `LIMIT/OFFSET`.

The current endpoint accepts only the canonical MVN system tenant scope.  Its
projection includes mapped offers of active suppliers and exposes only the
commercial fields required for selection.  It never exposes price-source,
credentials, contacts, contracts or internal notes.

## Follow-up phases

1. Add a system-admin-owned supplier visibility policy contract and migration.
2. Implement independent `all_active` against that policy, including facets.
3. Implement sponsored exact supplier allowlists with leakage tests for rows,
   counts, facets and sorts; then attach the approved dynamic policy to Andrey.

`TenantOffer` and `TenantCatalogGrant` remain storefront publication/price
contracts and are not repurposed as supplier entitlement.
