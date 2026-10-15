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

The workspace is in the core Manager menu immediately after orders. Canonical
MVN sees its master catalog. A partner sees only published complete systems
with an active offer and active catalog grant for the selected storefront;
retail prices come from that storefront's offers. Commercial metrics use
mapped offers of active suppliers and are calculated before pagination. Demo
read-only tenants and `test1` receive a synthetic purchase cost of 90% of RRC, falling back
to their storefront retail price when RRC is absent. The same synthetic cost
drives sorting and margin; supplier wholesale cost is never returned to demo
accounts. Mutations remain blocked by the demo policy. The endpoint never
exposes price-source, credentials, contacts, contracts or internal notes.

## Equipment selection and storefront categories

Manager starts across categories and filters by nominal capacity, indoor form,
heating temperature, Wi-Fi, inverter, brand/series and availability. Household
and semi-industrial categories remain separate on the public storefront. A
console is an indoor form, not an automatic semi-industrial classification:
standalone residential consoles remain household, explicitly designated
semi-industrial systems retain that category, and multi-split components remain
multi-split components.

The current Manager workspace selects complete single split systems only.
`Product.product_kind=complete_split_system` is the positive admission rule;
contradictory multi-split/component source types and the multi-split category
and a recorded indoor-unit count other than one are conservative vetoes. This
rule applies before count, sort and pagination,
to brand/series options, exact-ID comparison and price snapshots used by order
actions. The collection action checks the same rule after its existing catalog
access policy. The general catalog-management query reuses only the ordinary
filter conditions and continues to show components. A direct `category=multi`
request to this workspace is rejected with 422. Indoor form and household vs.
semi-industrial category never prove completeness.

Existing browser-stored selections retain their ID/title until checked against
the current selection API. Missing or ineligible choices are marked and block
new collection/order actions without editing saved orders or proposals. The
server repeats the eligibility check for every action. See the
[read-only equipment-kind audit](../catalog-decision-complete-split-audit.md)
for the historical semi-industrial classification gap and release gate.

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

`TenantOffer` and `TenantCatalogGrant` remain storefront publication/price
contracts. Supplier-specific entitlements, if needed, require a separate policy.

## Shared product reader

`GET /api/manager/tenant-catalog/products/{product_id}` is the shared read-only
card for the master catalog, partner catalog and equipment selection workspace.
It requires current Manager access and `catalog.master.read`. Partners can
browse all published master product content, matching the existing tenant
catalog list. System staff can also read unpublished master products. Missing
products and unpublished products requested by partners return 404; invalid
product IDs return 422. Authentication and selected storefront are resolved
on every request; an inaccessible storefront returns 403.

The explicit response contains plain-text description, deduplicated public
gallery, validated manual links and grouped technical specifications. The
shared normalizer resolves legacy aliases; registry definitions supply labels,
typed values and units. Every populated registered technical field is included,
with a short `summary_fields` projection for the card header. Unknown metadata
keys, private normalized helper fields, attachment provenance and raw supplier
records are excluded. New technical keys must be registered to appear here.

`allowed` and `effective_price` follow the existing tenant catalog offer
projection for the exact tenant and selected storefront. Missing, inactive,
unpublished or grant-fenced partner offers do not provide a price. This does
not hide published master content or create grants/offers. System staff receive
the master price; unpublished master products have `allowed=false`.

`selection_item` is nullable. Eligible published complete split systems receive
the existing decision projection with its current storefront/grant checks,
commercial policy and demo cost masking. Products outside selection scope,
including components and unpublished master products, receive null. Stock is
not required for selection. Reading the card changes no catalog, grant, offer
or basket and remains available in read-only demo accounts; order and collection
actions repeat their existing server checks.

The owner list opens this reader from the main card/table action; its separate
edit action keeps the existing editor and saved list context. Partner catalog
names and images open the same reader. Selection from either catalog stores
only ID/title in the existing 24-hour account basket. The contextual order
workspace keeps its separate order/proposal basket and marks existing lines.
The reader stays open after adding/removing; unavailable products remain
readable and cannot be added. All current order actions revalidate eligibility.

Search, stock, inverter, capacity and budget remain visible in the compact
filter bar. Other controls expand through “Все фильтры”; active criteria remain
visible as removable chips when collapsed, and retain the existing URL contract.
The narrow-screen sort is one select plus an explicit direction control. Browser
acceptance fixtures live in
[the visual checks](../../manager_frontend/tests/visual/catalog-reader/README.md).
