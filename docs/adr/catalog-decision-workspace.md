# Catalog Decision Workspace

## Status

Accepted. Catalog reads remain separate from the explicit collection/order actions.

## Decision

The Manager decision workspace is a separate server-side query projection,
not an extension of `ProductsView.vue` and not a post-pagination decoration by
`ProductSupplyMetricsService`.  Filters, active-supplier eligibility,
commercial aggregates, ordering, null semantics and the `Product.id` tie-break
are evaluated before `LIMIT/OFFSET`.

Cooling-power filters use one nominal cooling value: `Product.power_cooling`
with canonical `capacity_cooling_kw` as fallback. A kW range compares that
nominal directly. BTU pills use their canonical nominal-power band when it is
known; only a product without nominal capacity may use its area as a fallback.
Modulation min/max and digits in a product title never qualify a known nominal
for a different equipment size. Free-text search retains its flexible nominal
and title matching behavior.

The current endpoint accepts only the canonical MVN system tenant scope.  Its
projection includes mapped offers of active suppliers and exposes only the
commercial fields required for selection.  It never exposes price-source,
credentials, contacts, contracts or internal notes.

## Equipment selection and storefront categories

Manager starts across categories and filters by nominal capacity, indoor form,
heating temperature, Wi-Fi, inverter, brand/series and availability. Household
and semi-industrial categories remain separate on the public storefront. A
console is an indoor form, not an automatic semi-industrial classification:
standalone residential consoles remain household, explicitly designated
semi-industrial systems retain that category, and multi-split components remain
multi-split components.

Heating presets are -20, -25 and -30 Celsius. The typed outdoor heating minimum
is authoritative, with the legacy normalized minimum as fallback; a product
qualifies when its minimum is at or below the requested threshold. Missing or
malformed temperatures do not qualify. This states the operating temperature
limit, not the available heating capacity at that temperature.

## Selection from an order

The equipment button saves pending order edits before opening the catalog with
the exact order ID and currently open proposal ID. Failure keeps the order open.
The target is fetched on entry and checked again by the server when attaching.
The order must still be in negotiation and the proposal must belong to it, be
active and permit editing under the existing revision lifecycle.

`append_to_proposal` inserts missing product IDs using current catalog price and
cost snapshots. Existing quantities, prices, descriptions, logistics and service
lines stay intact; retries do not duplicate products. The order write lock
serializes concurrent edits. General catalog attachment modes remain available
outside this contextual flow.

The basket retains the 24-hour tenant/staff identity boundary and adds the order
and proposal IDs to its storage key. Successful attachment clears only that
basket and returns to the same proposal. Leaving without attachment preserves
the basket. A failed attachment leaves selection available for retry.

Historical products whose original console type was already overwritten need
source-backed correction; see [the equipment data audit](../catalog-decision-equipment-data-audit.md).
This change does not run a production backfill.

## Follow-up phases

1. Add a system-admin-owned supplier visibility policy contract and migration.
2. Implement independent `all_active` against that policy, including facets.
3. Implement sponsored exact supplier allowlists with leakage tests for rows,
   counts, facets and sorts; then attach the approved dynamic policy to Andrey.

`TenantOffer` and `TenantCatalogGrant` remain storefront publication/price
contracts and are not repurposed as supplier entitlement.
