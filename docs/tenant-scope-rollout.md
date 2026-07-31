# Tenant scope rollout contract

**Status:** accepted transitional contract for the MVN white-label rollout.

## Decision

`tenant_id` is the security boundary. `storefront_id` identifies the operating
storefront inside that tenant. Neither value is accepted from public or Manager
request payloads.

The rollout uses expand/backfill/contract releases:

1. **Expand and dual-write.** `Lead`, `Order`, `Customer` and requisites
   recognition receive nullable ownership keys with no database or Python
   default. Every production constructor requires an immutable
   server-resolved `TenantScope`. Customer belongs to a tenant; Lead and Order
   also retain the originating storefront.
2. **Backfill and verify.** Existing and mixed-version null rows are assigned to
   the canonical `mvn/main` scope. A report must show zero null, partial,
   unknown and cross-tenant references before contract.
3. **Contract and enforce.** Scope becomes mandatory and tenant-safe composite
   constraints, idempotency indexes, Manager authorization and query filters
   are enabled together.

Application rollback during the expand phase means rolling the image back while
keeping the additive schema. The migration refuses to drop provenance columns
after scoped rows exist.

## Current trusted resolvers

The browser currently sends public requests to the shared `api.mvn.by` origin.
The API `Host` therefore does not prove whether the request originated from
`mvn.by`, another city storefront or a forged client.

While MVN has exactly one public storefront, public, bot and email entrypoints
resolve the active system tenant `mvn` and its active default storefront `main`
from the database. Resolution fails closed when that pair is missing or
ambiguous. IDs are never hardcoded.

Manager requests resolve an active `TenantMembership`, its active tenant and
the tenant's active default storefront on every authenticated request. The
membership role is authoritative; a role stored in an old token is ignored.
Until the Manager UI has an explicit tenant switcher, zero or more than one
active membership candidate fails closed with `403`.

Before a second storefront is enabled, this temporary resolver must be replaced:

- public requests need a trusted proxy or signed server-to-server storefront
  context;
- Manager needs an explicit, server-validated membership selector before one
  user may actively work in more than one tenant;
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
- customer creation/reuse in those Order and Lead boundaries;
- customer requisites recognition and confirmation;
- the dormant legacy cart/DAO path.

Public checkout/contact/availability/installation/repair adapters, Manager
commands, equipment maintenance, the staff bot and email import must resolve or
receive that scope before entering those boundaries.

Public DTOs and Manager command payloads deliberately expose neither ID.

## Controlled historical backfill

`scripts/backfill_lead_order_tenant_scope.py` is the only supported write path
for historical Lead/Order provenance. It is dry-run by default and must run
inside the active API container on the current Patroni primary.

The dry-run:

- resolves `mvn/main` through the same fail-closed server resolver;
- reports legacy-null, target, partial, unexpected, unknown and cross-tenant
  rows independently for Lead and Order;
- selects at most `--limit` rows from each table;
- prints the exact candidate IDs and a SHA-256 plan token.

Example canary:

```bash
python3 scripts/backfill_lead_order_tenant_scope.py --limit 1
```

Execute only the `reviewed_execute_command` printed by that dry-run. The
command includes the resolved tenant/storefront IDs and plan token. Execute
rebuilds the plan under a transaction-scoped advisory lock, rejects a stale
token or any provenance anomaly, locks the selected rows and commits Lead and
Order updates together. The technical update preserves each row's existing
`updated_at`; provenance backfill must not change business recency, sorting or
archival behavior.

After the canary, repeat dry-run/execute with a larger bounded batch:

```bash
python3 scripts/backfill_lead_order_tenant_scope.py --limit 1000
```

Normal new writes already carrying the correct scope do not invalidate a
reviewed plan. A new legacy row, changed candidate set, partial pair, unknown
reference, cross-tenant pair or unexpected tenant/storefront does.

The backfill phase is complete only when a final dry-run prints:

- `legacy_null=0` for both tables;
- zero partial, unexpected, unknown and cross-tenant rows;
- `contract_ready=true`.

### Customer and requisites-recognition backfill

`scripts/backfill_customer_tenant_scope.py` is the only supported historical
write path for Customer and requisites-recognition ownership. It uses the same
bounded dry-run, exact candidate IDs, SHA-256 plan token, expected scope,
transaction advisory lock and stale-plan rejection as the Lead/Order backfill.

Run it before creating a second tenant with production data:

```bash
python3 scripts/backfill_customer_tenant_scope.py --limit 1
```

Execute only the printed `reviewed_execute_command`, then repeat with a bounded
larger batch:

```bash
python3 scripts/backfill_customer_tenant_scope.py --limit 1000
```

Completion requires `legacy_null=0`, `unexpected_scoped=0`,
`unknown_tenant=0` and `contract_ready=true` for both tables. The technical
recognition update preserves `updated_at`.

The additive migration also creates the missing system `TenantMembership` for
each existing staff identity. It does not overwrite an existing membership.
After deployment, Manager authorization and staff lists use membership
role/status and tenant ownership rather than the role copied into a token.

## What this release does not claim

This release isolates direct Customer reads/writes and customer-owned branches,
contracts, documents, reconciliation and requisites recognition. Manager
authentication and staff administration are membership-scoped, including
negative cross-tenant tests. Only the system tenant can see or claim legacy
nullable Customer rows during rollout.

It does not yet make the complete CRM safe for an external tenant. Order and
Lead read/update projections, equipment/service history, installer registry,
notifications and several child resources still need tenant-scoped query
boundaries and negative integration tests. Idempotency/reuse lookups
temporarily include legacy null rows only for the system tenant; their unique
indexes remain global until the contract migration. A second tenant with real
traffic or an external customer must not be enabled yet.
