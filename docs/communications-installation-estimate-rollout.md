# Installation-estimate communications rollout

`crm.installation_estimate_lead.created` is delivered only by the managed
communications worker. The standalone staff bot must remain limited to staff
task events, and this intake must not gain a direct `BotService` fallback.

The production website scope is deliberately exact:

- event: `crm.installation_estimate_lead.created`;
- template: `telegram.installation_estimate_lead_created`.

Public order/contact events and the operations canary are excluded. Expanding
the scope requires a separate reviewed rollout.

## Dormant compatibility-stage backlog suppression

Old installation-estimate events are not sent automatically after the worker
is enabled. Inventory covers both:

- stale `pending`/interrupted `processing` target outbox events;
- stale `published`/`processing` target events with `queued`, `retry`, or
  `running` Telegram deliveries.

This suppression is performed only in the earlier dormant (`false/false`)
compatibility stage, before the active worker profile is deployed. The managed
communications worker must be fully stopped, not merely paused: durable
Telegram state must report `mode=off` and `status=stopped`.

Production hosts are image-only. Resolve the current Patroni primary from a
trusted operator checkout, SSH to that node, and from its Compose project
directory resolve the active API slot:

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

"${BACKEND[@]}" scripts/reconcile_installation_estimate_backlog.py \
  --cutoff 2026-07-26T00:00:00+03:00 \
  --limit 100
```

The command is a privacy-safe dry-run unless `--execute` is provided. Its
output contains counts and fixed status codes only: no event IDs, aggregate
IDs, destinations, payloads, customer data or raw database errors.

After reviewing the dry-run, suppress the same bounded selection explicitly:

```bash
"${BACKEND[@]}" scripts/reconcile_installation_estimate_backlog.py \
  --cutoff 2026-07-26T00:00:00+03:00 \
  --limit 100 \
  --execute
```

`--execute` fails closed unless all of these conditions are true:

- `APP_ROLE=primary`;
- PostgreSQL is the writable primary and the transaction is not read-only;
- immutable deployment gates `COMMUNICATIONS_WORKER_ENABLED` and
  `COMMUNICATIONS_WORKER_ALLOW_ALL_MODE` are both `false`;
- the managed Telegram runtime advisory lock is available and remains held
  until commit or rollback;
- durable Telegram runtime control is `mode=off`, `status=stopped`;
- every selected event, delivery, and attempt journal has a recognized,
  internally consistent lifecycle.

SQLite and standby execution are rejected. Concurrently locked rows are skipped
with PostgreSQL `FOR UPDATE SKIP LOCKED`, remain visible in
`remaining_candidate_count`, and require another bounded pass.
The command also fails closed before loading or locking more than 5,000
deliveries or 40,000 attempt rows, even when a damaged event has abnormal
fan-out.

Safe outbox candidates transition to terminal `dead`. Their non-terminal
deliveries become `canceled`; a previously `running` delivery becomes `dead`
and its existing attempt is finalized with `ambiguous=true`, because a provider
request cannot be recalled or proven absent. A malformed or concurrently owned
lifecycle aborts the whole transaction with a fixed privacy-safe error code.

Repeat bounded execution as needed, then repeat the dry-run. Do not enable
delivery until `candidate_total=0`, `remaining_candidate_count=0`, and
`activation_safe=true`. The output contains counts and fixed codes only; it
must never contain event IDs, destinations, payloads, or customer data.

## Typed production control

There is no generic `all` switch. `CommunicationRuntimeStateService.set_mode`
rejects `all`, and operators must not replace the typed command with SQL or an
ad-hoc Python snippet. The only activation path is fixed to:

- event `crm.installation_estimate_lead.created`;
- template `telegram.installation_estimate_lead_created`;
- channel `telegram`;
- every active `StaffUser` whose primary role is `owner`.

Managers and `ADMIN_IDS` are never a fallback. Activation fails closed if
there are no active owners, if any active owner lacks a positive Telegram ID,
or if recipient keys or Telegram destinations are not unique.

Resolve the current primary and active API container as described in the HA
runbook, then define a command that runs inside the immutable backend image:

```bash
INSTALLATION_NOTIFICATIONS=(
  docker compose -f docker-compose.patroni.yml --profile bluegreen exec -T
  "${active_service}"
  python3 scripts/communications_installation_notifications.py
)
```

The CLI accepts exactly one of `--plan`, `--enable`, `--status`, and `--off`.
It has no event, destination, template, message, retry, or watermark argument.

`--plan` and `--status` remain available in dormant, canary, and active
deployment profiles. They return fixed codes and aggregate counts only. In a
canary (`true/false`) or dormant (`false/false`) profile, `--enable` is always
blocked:

```bash
"${INSTALLATION_NOTIFICATIONS[@]}" --plan
"${INSTALLATION_NOTIFICATIONS[@]}" --status
```

The status inventory always includes these explicit buckets, including zeros:

- outbox: `pending`, `processing`, `published`, `dead`;
- delivery: `queued`, `running`, `retry`, `sent`, `dead`, `canceled`;
- attempts: `running`, `sent`, `retry`, `dead`, `canceled`;
- provider acknowledgement count;
- `ambiguous_nonterminal_count`, `ambiguous_terminal_count`, and
  `ambiguous_total_count`.

It never prints event IDs, order IDs, destinations, payloads, rendered content,
customer data, tokens, connection strings, raw provider responses, or exception
messages.

## Activation transaction

Deploy the active (`true/true`) profile while durable runtime control is still
`off`. Then run `--plan`. Do not continue unless `enable_allowed=true` and the
blocker list is empty:

```bash
"${INSTALLATION_NOTIFICATIONS[@]}" --plan
"${INSTALLATION_NOTIFICATIONS[@]}" --enable
"${INSTALLATION_NOTIFICATIONS[@]}" --status
```

`--enable` locks the durable Telegram control row and proves all gates in one
database transaction:

- deployment profile is exactly active: worker enabled and `allow_all=true`;
- `APP_ROLE=primary`;
- PostgreSQL is the writable primary, not read-only or in recovery;
- transaction isolation is exactly PostgreSQL `read committed`;
- a non-placeholder Telegram token is configured;
- database runtime locks are enabled;
- exactly one fresh worker instance owns the expected advisory lock;
- runtime mode is `off` and lifecycle status is `disabled`;
- the exact owner audience is valid;
- no currently committed pending/interrupted target event, non-terminal target
  delivery, running target attempt, or ambiguous attempt attached to a
  non-terminal target delivery remains unreconciled, regardless of its stored
  `created_at`.

Every normal target-event enqueue first takes a shared transaction advisory
fence, then assigns the event `created_at` from the PostgreSQL clock. Shared
holders do not serialize ordinary requests. `--enable` makes a non-blocking
attempt to take the exclusive side of the same fence. If an enqueue transaction
is still open, activation fails immediately with
`installation_activation_fence_busy`, mutates no control state, and must be
rerun after that request finishes. It never waits indefinitely behind a stalled
request.

A request that reaches the enqueue fence while `--enable` holds its exclusive
side waits for at most one second. If activation does not finish in that bound,
the whole intake transaction and private attachment writes are rolled back and
the endpoint returns retryable HTTP `503` with `Retry-After: 1`. A client must
resubmit the same `Idempotency-Key`; the server never partially creates an
order or outbox event.

With `read committed` isolation, a successful exclusive fence proves that
earlier enqueue transactions are visible to the safety inventory; later
enqueues cannot obtain their database timestamp until activation commits. The
command then reads its cutoff from the same database clock. On the first
successful activation it stores that value as the immutable activation
watermark and increments the control revision. Dispatcher selection, delivery
claim, and expired-lease recovery all require
`IntegrationOutboxEvent.created_at >= watermark`; older events can never be
sent. Emergency `off` retains the watermark. A reviewed re-enable reuses the
same value and never moves it, and it first requires the whole currently
committed unsafe target inventory to be reconciled. This all-row inventory
also prevents a future-skewed timestamp from bypassing activation safety. Once
runtime mode is `all`, a missing watermark fails closed. A persisted future or
otherwise invalid watermark also blocks activation.

After activation:

1. Submit one new synthetic multipart request.
2. Verify one outbox event and exactly one delivery per current active owner.
3. Require a provider acknowledgement for every delivery and zero
   queued/running/retry/dead/canceled rows for the synthetic request.
4. Replay the identical request with the same `Idempotency-Key`.
5. Verify the replay creates no event, delivery, attempt, or provider call.
6. Have each owner confirm exactly one received message.

## Emergency off and ambiguity policy

`--off` is the independent emergency path. It does not require the active
profile, token, owner audience, or activation gates:

```bash
"${INSTALLATION_NOTIFICATIONS[@]}" --off
```

It commits `mode=off` first, retains the activation watermark, then waits for a
bounded drain and reports durable runtime mode/status, running delivery count,
ambiguous count, and whether drain completed. A timed-out drain is not a
successful operator result. Re-run it on the newly resolved writable primary
after a role change.

Telegram does not offer provider-side idempotency. Each attempt therefore has
a durable provider boundary committed under its exact worker lease, after
rendering, owner revalidation, and the final runtime safety check, immediately
before network I/O. `off` and the provider boundary serialize on the same
runtime-control row. If `off` commits first, the exact pre-provider claim is
released with no ambiguity, its lease is cleared, and it becomes a delayed
retry (or terminal non-ambiguous failure when attempts are exhausted). This
keeps the off drain live while leaving the retry backlog visible to the next
reviewed activation. An expired lease before that boundary is likewise provably
unsent and follows the same retry/exhaustion policy. An expired
lease after the boundary may have been accepted by Telegram and is always
terminal `dead` with `ambiguous=true`. A timeout, connection loss, server
failure, or malformed acknowledgement after the boundary follows the same
terminal policy. Authentication and Telegram 400-series request failures are
terminal as well.

The standalone staff bot receives a delivery payload from the API in another
process. That committed API handoff is itself its provider boundary. During a
rolling upgrade, even a legacy staff-bot claim with no marker is recovered
conservatively as post-boundary. Lost responses and bot crashes can therefore
never turn into an automatic duplicate send.

The sole automatic provider retry is an explicit Telegram 429 response with a
valid positive `retry_after`, because Telegram has proven that request was not
accepted for delivery. A historical terminal ambiguous attempt is permanently
counted, alerted, and retained for manual follow-up; claim selection can never
resurrect it. It does not become an eternal global re-enable blocker. Before
activation, `ambiguous_nonterminal_count` must be zero; terminal and total
counters must still be reviewed explicitly.
