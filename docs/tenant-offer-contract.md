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

The offer mutation and its `TenantAuditEvent` are committed in one transaction.
An audit write failure rolls the offer mutation back. Audit records include the
actor, request correlation ID and field-level before/after values. No Manager
endpoint mutates or deletes audit rows.
The audit stores both an immutable staff-user identifier when one exists and a
username snapshot; legacy system-admin commands may have only the snapshot.

## Database invariants

- one offer exists per `(tenant_id, storefront_id, product_id)`;
- the storefront must belong to the same tenant;
- price is non-negative and `old_price`, when present, is not below price;
- status is `active` or `disabled`;
- audit records carry the same tenant/storefront consistency constraint.

## Deliberate release boundary

This foundation does not change public catalog output. Until the next release,
public product endpoints continue using the existing MVN price and visibility.
The public cutover must join active, published offers inside the catalog SQL
query before filtering, sorting and pagination. Applying prices after
pagination would produce incorrect result sets and is prohibited.

For non-default storefronts the future public projection will be
deny-by-default: a product without an active, published offer is not visible.
The canonical `mvn/main` compatibility policy must be made explicit and tested
before that projection is enabled.
