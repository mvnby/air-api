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

## Explicit catalog group in the product editor

Product kind (complete system/component), indoor form and storefront group are
separate decisions. The main product editor exposes household, multi-split,
semi-industrial and automatic category assignment next to product kind. An
explicit choice is persisted in `Product.catalog_category_override`; null
returns to automatic inference. Existing products start with a null override,
and the additive migration does not move their category tags.

One category service synchronizes the category tag used by existing catalog
filters. A manual override wins over imported source classification and stale
category IDs in a full editor payload, and survives reimport and normalization.
Other tags, prices and the product's physical type are preserved. Duplicate
cards inherit the override unless explicitly reset. Ordinary price-only edits
do not silently recategorize automatic products; changing classification or
explicitly choosing Auto requests inference again.

Generic tag payloads preserve the stored category, including after an Auto
reset in a still-open editor; only the dedicated group choice or changed
classification inputs move it. Repairing category tag metadata also invalidates
the public catalog even when the product retains the same tag ID.

Category controls are removed from the generic tag picker so there is one
place to change the group. Source labels such as TCL's Light Commercial do not
prevent a manager from assigning a residential console to the household group.

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

## Selection workspace UX

The filter bar uses recognizable indoor-unit silhouettes and two capacity groups
(7–24 and 30–60 thousand BTU/h). Class 30 has a nominal band of 8.1–9.4 kW;
the area fallback applies only without a known nominal capacity. Unsupported
classes are rejected. Existing public installation range semantics are preserved.
Retail budget bounds are evaluated before both count and pagination. Stock is
the default; `include_orderable=true` explicitly requests all availability states.
Wi-Fi distinguishes a built-in module from an optional module.

Filter, sort and page criteria are stored in the URL without replacing order,
proposal or return-navigation parameters. Invalid URL values are ignored. Rows
remain visible but inactive while criteria are loading or a request has failed.
Filter-option failures have their own retry action.

The 24-hour basket continues to persist only IDs and titles, scoped to the
tenant, staff member and optional proposal. Comparing two to four models fetches
current values using `product_ids` and the same authorization/publication policy;
commercial values are never restored from browser storage. Quick model details
do not navigate away from the workspace. Prices use the official NBRB SVG sign,
with a textual BYN fallback for accessibility/copying; currency contracts stay BYN.

Order creation and general attachment distinguish a bundle from alternatives.
API callers retain `proposal_mode=bundle` by default for compatibility. The UI
defaults a multi-model selection to alternatives, one model per proposal.
Existing-order alternatives require `mode=new_alternative` and preserve populated
or locked proposals. An entirely empty selected draft can receive the first
alternative; remaining models receive new proposals. Exact-target `append_to_proposal` remains bundle-only. Quantities in a
bundle start at one and can be edited in the order. Creating proposals does not
send anything to the customer or publish a collection.

## Follow-up phases

1. Add a system-admin-owned supplier visibility policy contract and migration.
2. Implement independent `all_active` against that policy, including facets.
3. Implement sponsored exact supplier allowlists with leakage tests for rows,
   counts, facets and sorts; then attach the approved dynamic policy to Andrey.

`TenantOffer` and `TenantCatalogGrant` remain storefront publication/price
contracts and are not repurposed as supplier entitlement.
