# Tenant scope rollout contract

**Status:** accepted transitional contract for the MVN white-label rollout.

## Decision

`tenant_id` is the security boundary. `storefront_id` identifies the operating
storefront inside that tenant. Neither value is accepted from public or Manager
request payloads.

The rollout uses expand/backfill/contract releases:

1. **Expand and dual-write.** `Lead` and `Order` receive nullable keys with no
   database or Python default. Every production constructor requires an
   immutable server-resolved `TenantScope`.
2. **Backfill and verify.** Existing and mixed-version null rows are assigned to
   the canonical `mvn/main` scope. A report must show zero null, partial,
   unknown and cross-tenant references before contract.
3. **Contract and enforce.** Scope becomes mandatory and tenant-safe composite
   constraints, idempotency indexes, Manager authorization and query filters
   are enabled together.

Application rollback during the expand phase means rolling the image back while
keeping the additive schema. The migration refuses to drop provenance columns
after scoped rows exist.

## Current single-storefront resolver

The browser currently sends public requests to the shared `api.mvn.by` origin.
The API `Host` therefore does not prove whether the request originated from
`mvn.by`, another city storefront or a forged client.

While MVN has exactly one storefront, public, Manager, bot and email entrypoints
resolve the active system tenant `mvn` and its active default storefront `main`
from the database. Resolution fails closed when that pair is missing or
ambiguous. IDs are never hardcoded.

Before a second storefront is enabled, this temporary resolver must be replaced:

- public requests need a trusted proxy or signed server-to-server storefront
  context;
- Manager requests need an active `TenantMembership` context;
- scheduled integrations need a tenant-bound server configuration.

Plain `X-Tenant-*`, `X-Storefront-*`, query/body fields, `Origin`, or an
untrusted forwarded host are not accepted as authority.

## Constructor contract

The following root write boundaries require explicit `TenantScope`:

- `LeadService.create_lead`;
- `LeadService.qualify_lead` (the Order inherits the persisted Lead scope);
- `OrderService.create_from_website`;
- `OrderService.create_manager_order`;
- `OrderTransferService.import_orders`;
- the dormant legacy cart/DAO path.

Public checkout/contact/availability/installation/repair adapters, Manager
commands, equipment maintenance, the staff bot and email import must resolve or
receive that scope before entering those boundaries.

Public DTOs and Manager command payloads deliberately expose neither ID.

## What this release does not claim

The expand release records ownership provenance; it does not yet provide
multi-tenant isolation. `Customer`, Manager authorization, CRM reads, child
Order resources and notifications remain global until the contract release.
Idempotency/reuse lookups are tenant-aware but temporarily include legacy null
rows; their unique indexes remain global until backfill makes tenant scope
mandatory. A second tenant or external customer must not be enabled before
those boundaries and their negative integration tests are complete.
