# Tenant offer foundation contract

## Scope

`Product` remains the shared technical catalog record. `TenantOffer` is the
commercial projection for exactly one `(tenant, storefront, product)` tuple:
price, crossed-out price, lifecycle status and publication decision.

The Manager API never accepts `tenant_id` or `storefront_id`. Both values come
from the authenticated membership scope. Reads and writes use the exact pair,
so an opaque offer ID from another storefront returns `404`.

## Write boundary

`POST /api/manager/tenant-offers` is an idempotent upsert for the current
storefront and product. The command locks the shared Product row before it
looks up the scoped offer. Concurrent first writes for the same product are
therefore serialized before the database uniqueness constraint is reached.

`PATCH /api/manager/tenant-offers/{offer_id}` updates only an offer owned by the
current scope. Disabling an offer always unpublishes it. There is intentionally
no hard-delete endpoint; obsolete offers move to `disabled` so their history is
retained.

The offer mutation, its `TenantAuditEvent`, exact storefront revision and
durable cache-invalidation event are committed in one transaction. A failure
in any one of them rolls the entire command back. Cloudflare is never called
from that transaction. An identical offer upsert creates no audit event,
revision or invalidation. The delivery contract is documented in
[`catalog-cache-invalidation.md`](catalog-cache-invalidation.md).

Audit records include the actor, request correlation ID and field-level
before/after values. No Manager endpoint mutates or deletes audit rows.
The audit stores both an immutable staff-user identifier when one exists and a
username snapshot; legacy system-admin commands may have only the snapshot.

## Database invariants

- one offer exists per `(tenant_id, storefront_id, product_id)`;
- the storefront must belong to the same tenant;
- price is non-negative and `old_price`, when present, is not below price;
- status is `active` or `disabled`;
- audit records carry the same tenant/storefront consistency constraint.

## Public catalog projection

The canonical `mvn/main` storefront intentionally keeps the historical shared
`Product.price` behaviour, but it can expose only published products. Every
other trusted storefront is deny-by-default and reads only a globally
published Product with an exact `(tenant_id, storefront_id)` offer where
`status=active` and `is_published=true`.

Offer price is joined in SQL before price filtering, sorting, counting and
pagination. It is not overlaid after a shared catalog page has been selected.
The same boundary applies to product detail, siblings, series navigation,
featured products, brand counts, series pages, merchandising collections,
filter metadata, spec keys and the legacy public search endpoint.

Public product payloads serialize a tag only when both `Tag.is_public=true`
and its `TagGroup.is_public=true`. Catalog tag filters and tag-title search use
the same predicate. Hidden tag slugs are ignored exactly like unknown legacy
slugs; a legacy brand slug is recognized only through a public brand tag and a
published `Brand`. These rules are identical for the canonical and secondary
storefront projections.

Website checkout resolves and share-locks the same storefront price again on
the server, in deterministic product order, before creating any order rows. A
missing or disabled offer returns `409 product_not_available`; a valid order
stores the storefront unit price in `OrderProductLink.price` and records the
pricing source in the order technical snapshot. Link creation receives the
locked price through a dedicated immutable command, so the generic order
orchestrator does not resolve or fall back from storefront pricing.
Browser-supplied prices remain non-authoritative.

`POST /api/v1/leads/product-availability` applies the same visibility check
before looking up or creating an Order and before resolving notification
recipients. A foreign, disabled or missing offer returns the same neutral `404`
as a missing Product and has no persistence or notification side effects.
