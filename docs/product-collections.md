# Product collections

Product collections are the canonical merchandising source for reusable storefront
slots. Collection records keep editorial intent and product references only. Prices,
images, specifications, features, and availability always come from the current
public product mapper.

## Boundaries

- `ProductCollection` owns public copy, status, limits, schedule, and fallback.
- `ProductCollectionItem` owns manual order and optional internal notes.
- `ProductCollectionPlacement` assigns a collection to a `surface/slot`.
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
- Public placement:
  `/api/v1/content/placements/{surface_key}/{slot_key}/collections`

The public placement endpoint omits inactive collections and collections that do not
reach `min_items`. A valid fallback may supply the items while the original
collection retains its editorial title and placement.

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
