# Manager storefront selector contract

## Trust boundary

The authenticated membership resolves the tenant first. A Manager client may
then request one active storefront inside that tenant with
`X-MVN-Manager-Storefront: <slug>`.

The header is not a tenant selector and never broadens membership access. The
server normalizes the slug and looks it up with the already authenticated
`tenant_id`. Unknown, disabled, malformed and foreign storefront slugs all fail
with the same `403 Storefront access denied` response.

If the header is absent, every existing Manager client keeps using the active
default storefront. Multi-tenant membership remains fail-closed and cannot be
resolved by this header; a future tenant switcher requires its own explicit
contract.

## Discovery

`GET /api/manager/storefronts` returns active storefronts for the authenticated
tenant. The response exposes stable slugs and display configuration, but not
database IDs. Exactly one item matches the request's resolved storefront.

## Data isolation

The selected storefront becomes the normal `AuthenticatedUser.tenant_scope()`.
Existing service and CRUD predicates therefore apply it to Lead, Order,
Customer-facing workflows and TenantOffer without accepting scope fields in
payloads. System-only Manager surfaces remain system-only because storefront
selection cannot change the authenticated tenant.

The selector is infrastructure for the internal second-storefront canary. It
does not itself add a Vue switcher and does not enable public traffic.
