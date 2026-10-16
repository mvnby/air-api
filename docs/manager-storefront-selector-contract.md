# Manager storefront selector contract

## Trust boundary

The browser first reads `GET /api/manager/account/companies` using its live
personal identity. This bootstrap ignores selected company/site headers and
returns active workspace memberships, or virtual support choices for the
verified platform owner. No support membership is inserted into the database.

`X-MVN-Manager-Tenant: <positive ID>` explicitly selects an accessible company.
The server resolves company access before applying
`X-MVN-Manager-Storefront: <slug>` inside that company.

The storefront header never broadens company access. The
server normalizes the slug and looks it up with the already authenticated
`tenant_id`. Unknown, disabled, malformed and foreign storefront slugs all fail
with the same `403 Storefront access denied` response.

An absent storefront header uses the active default site. An ordinary person
with several eligible companies must select one explicitly; ambiguous business
requests return `409/company_selection_required`. Invalid explicit choices fail
closed and never fall back to another company. The bound platform owner's
canonical membership remains the default. Virtual partner support does not move
the owner's personal profile, installer link or connector grants.

## Discovery

`GET /api/manager/storefronts` returns active storefronts for the authenticated
tenant. The response exposes IDs, stable slugs, primary hostnames and display
configuration. Exactly one item matches the request's resolved storefront.
Company owners/admins can inspect draft/disabled sites and all domain states at
`GET /api/manager/company/sites`; this endpoint cannot change DNS or publish sites.

## Data isolation

The selected storefront becomes the normal `AuthenticatedUser.tenant_scope()`.
Existing service and CRUD predicates therefore apply it to Lead, Order,
Customer-facing workflows and TenantOffer without accepting scope fields in
payloads. System-only Manager surfaces remain system-only because storefront
selection cannot change the authenticated tenant.

## Browser selection

Manager displays company and site selectors, including when there is one choice.
Selection is scoped to the person and browser tab in `sessionStorage`. Switching
passes the unsaved-changes guard; the currently rendered page keeps its current
request headers until the next page bootstrap. Canceling navigation therefore
cannot leave old content operating in a new company.

Links may select `company=<ID>&site=<slug>`. Explicit URL choices are validated
before business screens load; an invalid link displays an access error without
loading another company's order. A stale remembered selection may recover to an
available default. Manual switching removes the old context query parameters.

Personal profile, password and Telegram settings resolve an actual personal
membership independently of browser selection. Private image requests explicitly
carry `tenant_id` in their URL because browser images cannot add selection headers;
the server validates that access before returning either bytes or `304`.
