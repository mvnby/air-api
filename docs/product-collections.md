# Product collections

Product collections are the canonical merchandising source for reusable storefront
slots. Collection records keep editorial intent and product references only. Prices,
images, specifications, features, and availability always come from the current
public product mapper.

## Boundaries

- `ProductCollection` owns public copy, status, limits, schedule, and fallback.
- `ProductCollectionItem` owns manual order and optional internal notes.
- `ProductCollectionPlacement` assigns a collection to a `surface/slot`.
- Placement presentation (`display_mode`, `item_limit`, `grid_columns`,
  `rotation_mode`) belongs to that assignment, so one collection can have different
  layouts on different pages. Collection minimum, fallback and schedules remain
  canonical resolver policy.
- `ProductCollectionResolver` is shared by Manager preview and the public API.
- `ProductCollectionEligibility` protects each placement from unsuitable products.
- `product.product_kind` is the explicit product taxonomy. It is never inferred from
  a title. The migration and write service derive it only from canonical component
  flags when both flags are conclusive.

For `home/featured_products`, only `complete_split_system` products are eligible.
The product must also be published and have a slug, price, main image,
`specs.area_m2`, and a normalized availability state.

## API

- Manager CRUD: `/api/manager/product-collections`
- Manager preview: `/api/manager/product-collections/{id}/preview`
- Atomic editor save: `PUT /api/manager/product-collections/{id}/workspace`, with
  `{collection, items, placements}`. All three parts, the audit entry and catalog
  invalidation outbox commit together. Existing partial endpoints stay compatible.
- Public placement:
  `/api/v1/content/placements/{surface_key}/{slot_key}/collections`

The public placement endpoint omits inactive collections and collections that do not
reach `min_items`. A valid fallback may supply the items while the original
collection retains its editorial title and placement.

## Editing and placement presentation

Manager separates the list from the selected editor. Changes stay local until an
explicit save; there is no autosave or separate persisted draft revision of a
published collection. New records are created as drafts before the first complete
workspace command. A failed workspace command leaves that draft available for retry.

Supported storefront locations are `home/featured_products`, `home/after_featured`,
`home/product_of_day`, `catalog/before_products`, `catalog/after_products` and
`article/<slot>`. Existing custom keys are preserved. The storefront implementation
and MDX article component live in `mvnby/mvn-web`; Manager can copy the insertion
snippet, but does not provide an article CMS.

Layouts are `carousel`, `grid`, `tiles` and `single`. Optional `item_limit` is 1–24;
`grid_columns` is 2–4. Presentation is applied after eligibility, collection
minimum and fallback resolution. A layout limiting the result to one product does
not change the minimum eligibility needed for the underlying collection.

`rotation_mode=daily` is valid only with `single`. The UTC date selects one eligible
daily collection among daily placements of the same slot, then one of its products.
Ordinary placements of that slot are unaffected. Stable ordering makes the result
consistent between requests. The saved-collection preview shows that collection's
layout and daily product, not whether it wins today's competition with sibling
daily collections. The browser refreshes dynamic blocks on entry, return to the
page and UTC rollover. MDX article blocks fetch only at runtime to avoid embedding
stale commercial data into static article HTML.

Migration `e61d4e5f6a7` initializes existing `home/featured_products` placements as
four-column grids and other existing placements as carousels. This preserves the
legacy desktop home layout. New generic placement defaults are carousel/three
columns/no rotation. Deploy the additive API migration before the dependent
Manager/storefront functionality; old public clients ignore the new response fields.

## Automatic and hybrid modes

Automatic and hybrid modes extend the existing resolver:

1. evaluate typed, allow-listed rules;
2. place valid pinned items first;
3. fill remaining positions with stable automatic results;
4. remove duplicates;
5. run the same eligibility checks;
6. apply `min_items` and fallback exactly once.

Do not add snapshots of commercial product data or execute user-defined expressions.

`rule_config` is a typed allow-list rather than a generic expression language. It
supports product kind, price, area, minimum indoor noise, minimum outdoor heating
temperature, inverter state, Wi-Fi state, brand, series, color, resolved Feature,
and public stock state. Every populated condition is combined with AND semantics.
Multiple values inside one condition use OR semantics, except `feature_ids`, where
all selected Features must be effective for the product.

Automatic results use one of the stable catalog sort modes. Hybrid results always
place valid pinned items first, then fill the remaining capacity with automatic
results while removing duplicates.
