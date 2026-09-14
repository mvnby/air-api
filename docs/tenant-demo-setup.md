# Read-only tenant demo fixture

This procedure prepares one existing partner storefront for a shared Manager
demo. It is deliberately narrow: three clearly marked synthetic customers, two
example orders with selected proposals, and the tenant-level read-only policy.
It does not create staff access, change the shared demo password, copy real CRM
records, or modify offers, tariffs, requisites, grants, documents, integrations,
or notification queues.

## Supported target

The exact tenant/storefront pair must already exist and satisfy all of these
conditions:

- the tenant is active, non-system, and `independent_seller`;
- the storefront is active and is the tenant's default storefront;
- the tenant contains no customers and this storefront contains no orders or
  leads;
- at least two target offers are active, published, publicly allowed by the
  current offer/grant contract, backed by published products, and have a
  positive retail price.

The fixture selects the first two eligible target offer IDs deterministically.
Their target retail prices become the example order and product-line prices.
Purchase and installation costs remain zero. The script never reads or copies a
customer from another tenant or a CRM source. Demo email addresses use the
reserved `example.invalid` domain, phone fields say `Не указан (демо N)`, and
the fictional company has no INN.

## Review-only plan

Read [production data operations](production-data-operations.md),
[deployment](deployment.md), [API HA](api-ha-runbook.md), and the current
[quorum procedure](postgres-quorum-runbook.md) before a production run.

The command defaults to a read-only transaction. For the current Test 1 target,
the exact plan command is:

```sh
python3 scripts/setup_tenant_demo.py plan --tenant-id 35 --storefront-id 36
```

Review the complete JSON report. It must identify tenant `35` and storefront
`36`, show `tenant_demo_read_only=false`, empty `customer_ids`, `order_ids`, and
`lead_ids`, two positive-price `chosen_offers`, `status=planned`, and an empty
`blockers` list. This is the dry-run proof that the target remains empty and the
fixture will use only current target offers. Keep the report as the review
artifact; do not execute a command copied from another run.

The plan digest covers the exact target identity and timestamps, current demo
flag, CRM inventory, any prior fixture identity, eligible-offer count, and the
chosen offers including their IDs, product IDs, retail prices, publication
state, grants, and update timestamps. The emitted plan token expires after 15
minutes. A changed offer or target state makes execution fail closed and
requires a fresh plan.

## Production execution gates

Execution is a manual production data mutation. Before running it:

1. Deploy the exact CI-tested immutable backend image to both API nodes and pass
   the required `/api/health`, products, and filter-config smoke checks.
2. Prove the full Patroni/etcd quorum healthy and exactly one writable primary.
   Stop if topology is degraded, ambiguous, or changes during the operation.
3. Resolve the active primary's exact pinned immutable app container. Run both
   plan and execute in that same image and environment; a local checkout or a
   mutable image tag is not an execution source.
4. Hold the normal per-project deployment lock for the plan/execute window and
   prevent an overlapping backend release or production data operation.
5. Review the fresh plan artifact, then run only its exact
   `reviewed_execute_command` on the proved primary.

Execution creates all fixture records, their identity record, and
`Tenant.demo_read_only=true` in one caller-owned transaction. A retry with an
intact matching fixture returns `status=already_ready` and creates no duplicates.
Existing or conflicting CRM data, missing fixture rows, changed cost markers,
an ineligible recorded offer, or a disabled demo policy is reported as a
blocker. The operation has no cleanup or reset mode.

After the seed commits, run a fresh plan again. Safe proof is
`status=already_ready`, empty blockers, the same recorded customer/order/offer
IDs, and no duplicates. Then provision the demo staff access through the
separately reviewed tenant-manager procedure. Do not create the shared demo
account before the read-only policy and seed are active.

## User-visible policy

The shared visitor password is managed outside this fixture and a visitor cannot
change it. Authenticated reads and the allowlisted pure calculator POST continue
to work. Saving or editing CRM/catalog/settings, sending messages or documents,
and connecting OAuth or other integrations return HTTP 403 for this demo tenant.
Normal tenants keep their existing behavior.

This fixture writes directly to scoped CRM models so it cannot invoke SMS,
email, Telegram, document, bot, OAuth, or outbox side effects. Verification must
confirm the two retail totals are visible, purchase costs are absent, and write
attempts fail with 403. A rollback or cleanup requires a separate reviewed data
operation; do not delete fixture rows ad hoc.

After shared demo access is issued, never roll the API back to an image that
predates the server-side demo policy. Such an image ignores
`Tenant.demo_read_only` and can allow owner writes. Use a forward fix. If an old
image must be restored, first disable the demo membership or credential through
a separate reviewed operation and prove the shared visitor can no longer log in.
