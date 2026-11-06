# Incoming communications rollout

This runbook covers the managed Telegram worker for the reviewed tenant incoming
notification allowlist. The historical filename is retained because operator
automation already refers to it; the runtime is no longer installation-only.

The fixed production allowlist is:

| Event | Template |
| --- | --- |
| `crm.installation_estimate_lead.created` | `telegram.installation_estimate_lead_created` |
| `tenant.website.checkout.created` | `telegram.tenant_website_checkout_created` |
| `tenant.website.contact_lead.created` | `telegram.tenant_website_contact_lead_created` |
| `tenant.website.product_availability.requested` | `telegram.tenant_website_product_availability_requested` |
| `tenant.website.repair_diagnostic.created` | `telegram.tenant_website_repair_diagnostic_created` |
| `tenant.incoming.created` | `telegram.tenant_incoming_created` |

The generic event covers newly created non-website raw leads, non-website inbox
orders and imported procurement requests. Website producers keep their existing
specific events. Qualification of a saved raw lead does not produce another
new-request alert. The record and event commit together; retries reuse the
event identity. The former email-import batch alert is replaced by individual
durable incoming alerts.

Every event resolves active owner/admin memberships inside its exact tenant and
storefront. There is no manager, global admin, or `ADMIN_IDS` fallback. The
standalone staff bot remains limited to staff-task events.

## Deployment profiles

The two HA Compose files must carry the same immutable worker profile.

- Dormant reconciliation: `COMMUNICATIONS_WORKER_ENABLED=false`,
  `COMMUNICATIONS_WORKER_ALLOW_ALL_MODE=false`.
- Exact canary: `true/false`.
- Full allowlist: `true/true`, only after a separate reviewed activation.

This preparation release pins both Patroni nodes to the dormant `false/false`
profile so the reviewed old backlog can be reconciled. Before deployment, use
the emergency-off command below and verify that in-flight work has drained.
Deploying it does not activate `all` mode. Do not edit one node independently:
profile changes use the existing attested HA rollout.

An earlier deployment can leave `mode=all` with a canary profile. A fresh
heartbeat with `status=paused` and `last_error_code=all_mode_not_enabled` proves
that no production delivery is running; a live process alone does not prove
notification health. Do not simply switch the profile to active while that
control state and an unreviewed backlog remain.

## Complete backlog manifest

Before any full activation, inventory every allowlisted event type. Use the
canonical command; `reconcile_installation_estimate_backlog.py` remains only
as a compatibility entrypoint for older installation-only automation and is not
sufficient evidence for the complete activation scope.

Production hosts are image-only. Resolve the writable Patroni primary and the
active API slot, then run inside that immutable backend image:

```bash
python3 scripts/ha/check_patroni_production.py --resolve-primary

active_service=app
if test -f .active-api-slot; then
  active_slot="$(tr -d '\r\n' < .active-api-slot)"
  case "${active_slot}" in
    blue|green) active_service="app-${active_slot}" ;;
    *) echo "invalid active API slot" >&2; exit 1 ;;
  esac
fi

BACKEND=(
  docker compose -f docker-compose.patroni.yml --profile bluegreen exec -T
  "${active_service}" python3
)
```

Prepare one UUID operation ID and one reviewed cutoff, count, and disposition
for each type. Every flag is positional and repeated six times:

```bash
operation_id="$(python3 -c 'import uuid; print(uuid.uuid4())')"
cutoff=2026-08-01T00:00:00+03:00

"${BACKEND[@]}" scripts/reconcile_website_communication_backlog.py \
  --operation-id "${operation_id}" \
  --event-type crm.installation_estimate_lead.created \
  --cutoff "${cutoff}" --expected-count 0 --disposition terminal_no_send \
  --event-type tenant.website.checkout.created \
  --cutoff "${cutoff}" --expected-count 0 --disposition terminal_no_send \
  --event-type tenant.website.contact_lead.created \
  --cutoff "${cutoff}" --expected-count 0 --disposition terminal_no_send \
  --event-type tenant.website.product_availability.requested \
  --cutoff "${cutoff}" --expected-count 0 --disposition terminal_no_send \
  --event-type tenant.website.repair_diagnostic.created \
  --cutoff "${cutoff}" --expected-count 0 --disposition terminal_no_send \
  --event-type tenant.incoming.created \
  --cutoff "${cutoff}" --expected-count 0 --disposition terminal_no_send
```

Dry-run is the default. Replace each expected count with the reported exact
candidate count, choose a reviewed disposition, rerun dry-run, then add
`--execute`.

- `retain` performs inspection only and always blocks activation.
- `terminal_no_send` marks the selected outbox rows terminal and closes every
  non-terminal delivery without a provider call.
- An ambiguous attempt is preserved as ambiguous and can never be claimed
  again. It is never converted into a retry.
- Execution requires a manifest containing each of the six types exactly once.
  A count change, lock conflict, malformed lifecycle, ownership conflict, or
  inventory overflow aborts the whole transaction.
- Execution is accepted only on the writable primary while the managed runtime
  is stopped/off, both deployment gates are false, and the runtime advisory lock
  remains held through commit.

The report is per event type and contains aggregate counts plus the operation
UUID. It never contains payloads, destinations, rendered messages, customer
data, tokens, connection strings, or raw database errors. Do not continue until
all six entries have `remaining_candidate_count=0`, no retain disposition,
and the manifest reports `activation_safe=true`.

Each `--execute` UUID creates a durable PII-free operation audit before the
mutation transaction. The audit stores the canonical six-entry manifest and
its SHA-256 plus aggregate per-type counts only. Event mutations and a
`succeeded` outcome commit atomically. A blocked or failed execution first
rolls back every event/delivery mutation, then durably records the fixed failure
outcome. Replaying the same UUID and exact manifest resumes a stranded
`started` operation or returns its terminal result; the same UUID with any
manifest difference is rejected. The operation row remains locked while a
SAVEPOINT contains the mutable reconciliation, so a blocked or failed outcome
is committed before any concurrent replay can proceed. Audit rows cannot be
deleted or rewritten.

The later activation command re-acquires the exclusive website enqueue fence
and re-queries the complete six-type backlog in the same transaction. A stale
manifest report cannot authorize activation.

## Full activation

After the explicitly approved backlog operation succeeds, release matching
`true/true` profiles on both nodes through the normal CI and attested HA
deployment. Keep runtime control `off` throughout this deployment. Run
`scripts/communications_installation_notifications.py --plan` inside the active
**communications worker** container so inspection uses its actual deployment
gates; the API container intentionally has different defaults. Only a plan
without blockers permits `--enable`. The command rechecks the complete backlog
and current recipients atomically. Never override a blocker with direct SQL.

The recipient readiness gate checks the server-resolved canonical MVN tenant
and storefront. Missing or ambiguous canonical scope, or invalid canonical
owner/admin recipients, blocks activation. An unrelated partner without a
linked Telegram account does not block MVN readiness. This gate does not alter
routing: every event still resolves and revalidates its exact tenant's audience,
and an unconfigured partner event cannot fall back to MVN recipients. Backlog
and delivery safety checks continue to cover all six types across all tenants.

Verify `--status`, a fresh heartbeat, `mode=all`, `status=running`, no runtime
error, and the existing API smoke checks. A real new incoming must produce its
outbox event and a provider-acknowledged `sent` delivery for each intended
recipient. Do not create a fictitious customer request for a smoke test.
If no new incoming occurs during verification, report that delivery evidence is
pending rather than claiming an end-to-end send. Emergency-off below is the
immediate rollback and preserves all source requests and delivery evidence.

## Exact website canary

The canary consumes one already committed, due, untouched outbox event. It does
not create a synthetic customer request and cannot broaden to a second event or
recipient. Pick one eligible `staff:<id>` from the full current directory for
that exact tenant/storefront.

The immutable canary target is:

- one run UUID;
- one 32-character event ID and its allowlisted event type;
- one tenant ID and storefront ID;
- one eligible recipient key.

No destination, payload, rendered message, or customer data is stored in the
canary audit row. Runtime state stores only the canary kind and a foreign-key
reference to that immutable row.

Run `--plan` first:

```bash
WEBSITE_CANARY=(
  "${BACKEND[@]}" scripts/communications_website_canary.py
  --run-id 11111111-1111-4111-8111-111111111111
  --event-id 0123456789abcdef0123456789abcdef
  --event-type tenant.website.contact_lead.created
  --tenant-id 7
  --storefront-id 11
  --recipient-key staff:9
)

"${WEBSITE_CANARY[@]}" --plan
```

Planning and arming fail closed unless all of these remain true:

- deployment profile is exactly `true/false`;
- the command runs on writable PostgreSQL primary with a real Telegram token;
- runtime is `off`, `disabled`, freshly owned, and at the planned control
  revision;
- the exact event is pending, due, has zero attempts and no lease, inbox,
  delivery, or attempt journal;
- event type, template, audience, payload tenant, and payload storefront match;
- the complete current tenant directory contains exactly one matching recipient
  key. Other eligible owner/admin recipients are normal and do not invalidate
  the canary.

Arm using the revision returned by plan:

```bash
"${WEBSITE_CANARY[@]}" --arm --expected-control-revision 42
"${WEBSITE_CANARY[@]}" --status
```

Dispatcher selection, materialization, delivery claim, lease recovery,
recipient revalidation, and the final provider-boundary lock all carry the same
exact event and recipient scope. A control revision change or any event,
tenant, storefront, template, or recipient drift stops before provider I/O.
At the provider boundary the same transaction locks the owned delivery and
attempt together with all control evidence in one fixed order: runtime state,
canary run, event, consumer inbox, delivery, storefront, selected staff user,
exact tenant membership, then delivery attempt. It rechecks active owner/admin
membership and the current Telegram destination before recording
`provider_started_at`. A concurrent role revoke, staff disable, destination
change, completion, or emergency-off therefore commits either before the
boundary (the delivery is canceled with no provider call) or after it.

After status reports a terminal `sent`, `dead`, `canceled`, or
`ambiguous` outcome, finalize it:

```bash
"${WEBSITE_CANARY[@]}" --complete
```

Finalization locks the runtime row, immutable run, event, inbox, delivery, and
attempt evidence in one transaction. It recomputes the deterministic delivery
ID and render-context fingerprint, verifies the full immutable delivery
snapshot and current locked recipient directory, and rejects contradictory
attempt journals. Any ambiguous attempt takes priority over a nominal sent
row. It then records the terminal outcome and an off revision and clears only
the active runtime reference. Replaying the exact active arm is idempotent;
reusing a completed run ID or event is rejected. The canary-run audit itself is
database append-only: only one armed-to-terminal transition is permitted.

## Emergency off and ambiguity

The compatibility control command still owns the independent emergency path:

```bash
"${BACKEND[@]}" scripts/communications_installation_notifications.py --off
```

Its name is historical; help and status cover the full six-type incoming
allowlist. Emergency off needs no token or recipient lookup. If a website canary
is active, it first records terminal `aborted` in the durable canary audit and
then clears the runtime reference. If that audit cannot be verified, off fails
with an explicit blocker instead of erasing the target.

Telegram has no provider-side idempotency. A timeout or lost response after the
durable provider boundary is ambiguous and is never automatically resent.
Only a proven Telegram 429 response with a valid positive retry delay is safe
for automatic retry. Provider acknowledgement is required before a canary is
classified as sent.
