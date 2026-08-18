# System-owned shared catalog grants

`TenantCatalogGrant` is the explicit authorization for one non-system
tenant/storefront to use the shared master catalog. The first and only supported
policy is `all_published` with `inherit_master` pricing. No public query infers a
grant from an empty offer list: a product still requires a materialized,
scope-exact `TenantOffer`.

## Data and visibility contract

- One grant is allowed per `(tenant_id, storefront_id)`. Its composite foreign
  key is repeated on every grant-managed `TenantOffer`, so an offer cannot point
  at another tenant's grant.
- A grant is always `owner_type=system`; there is no tenant-manager mutation
  route. The only write path is the reviewed operator CLI.
- `syncing` and `disabled` grants are invisible. Public catalog and checkout
  reads accept grant-managed offers only when the exact grant is `active`.
  Therefore initial multi-batch projection and multi-batch disable never expose
  a partial catalog.
- Newly materialized prices use `price_source=inherited_master` and are refreshed
  from `Product.price/old_price` on every sync. An existing manual offer may be
  adopted by the grant; it keeps `price_source=manual` and its price. This is the
  intentional extension point for a future reviewed storefront price override.
- `Product.is_published=false` hides a product immediately even before the next
  sync. The next sync disables its offer. A later republish remains hidden until
  sync explicitly reactivates it. Product deletion remains protected by the
  existing `TenantOffer` foreign key.
- Invalid master prices (`price < 0` or `old_price < price`) block planning; they
  are never deferred to a database constraint failure during execution.

## Transaction and concurrency contract

Planning is read-only. Every execution requires the exact signed token from a
fresh plan; the token expires after 15 minutes. Execution takes a
transaction-scoped advisory lock for the scope, then locks tenant/storefront,
grant, selected products, and selected offers in deterministic order. At most
the manifest's `batch_size` (maximum 200) offer changes are written per
transaction.

Each changed batch atomically writes the grant/offer projection, one exact audit
record, the contextual catalog revision, and the cache-invalidation outbox event
when the storefront is routable. A failure in any of those writes rolls the
whole batch back. Draft storefronts intentionally defer invalidation until the
normal storefront activation transaction, which now enumerates all visible
grant offers rather than the bounded onboarding canary list.

## Polotsk activation sequence

This change does not execute any production mutation. After the reviewed
storefront bootstrap has created `polotsk/main`, generate the first plan:

```bash
python3 scripts/manage_shared_catalog_grant.py plan \
  --manifest config/shared_catalog_grants/polotsk.json \
  --desired-status active
```

Review `blockers`, `scope`, `grant_change`, `batch_changes`, both fingerprints,
and the emitted `reviewed_execute_command`. Execute only that exact command.
Repeat with a new plan/token until the result reports `complete=true` and
`grant_status=active`. The Polotsk storefront must remain `draft` during this
initial multi-batch grant activation.

Then continue the existing domain verification and storefront activation flow.
Activation stages one revision/outbox transaction containing every currently
visible offer, not merely the first 100 onboarding exceptions. Before DNS
cutover, verify the exact Polotsk tenant context, product count, inherited/manual
price sources, checkout snapshots, and a negative query through another tenant.

Routine master-catalog changes use the same plan/execute loop. An already active
grant stays active during a bounded resync; unchanged products remain available,
and each committed batch receives its own revision/outbox invalidation.

## Disable, rollback, and migration

To remove the authorization, plan `--desired-status disabled`, execute the fresh
command, and repeat until `complete=true`. The first committed batch sets the
grant to `disabled`, which hides every linked offer atomically; later batches are
cleanup only. No offers, CRM rows, or audit history are deleted. Re-enable only
while the storefront is non-routable (`draft`), then complete all batches before
storefront activation.

The schema migration is additive and performs no automatic data backfill.
Existing offers default to `price_source=manual` and remain ungranted until an
operator explicitly runs the sync. Before an intentional Alembic downgrade,
disable the grant and complete cleanup. The downgrade also forcibly disables
all still-linked grant offers before removing ownership columns, so rollback
fails closed rather than turning them into ordinary visible offers.
