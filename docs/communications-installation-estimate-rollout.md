# Installation-estimate communications rollout

`crm.installation_estimate_lead.created` is delivered only by the managed
communications worker. The standalone staff bot must remain limited to staff
task events, and this intake must not gain a direct `BotService` fallback.

The production website scope is deliberately exact:

- event: `crm.installation_estimate_lead.created`;
- template: `telegram.installation_estimate_lead_created`.

Public order/contact events and the operations canary are excluded. Expanding
the scope requires a separate reviewed rollout.

## Stale backlog decision

Old installation-estimate events are not sent automatically after the worker
is enabled. Inventory covers both:

- stale `pending`/interrupted `processing` target outbox events;
- stale `published`/`processing` target events with `queued`, `retry`, or
  `running` Telegram deliveries.

Inventory and suppression use the immutable backend image. Before execution,
the managed communications worker must be fully stopped, not merely paused:
the durable Telegram runtime state must report both `mode=off` and
`status=stopped`.

```bash
cd /opt/air-api
docker compose -f docker-compose.prod.yml exec -T app \
  python3 scripts/reconcile_installation_estimate_backlog.py \
  --cutoff 2026-07-26T00:00:00+03:00 \
  --limit 100
```

The command is a privacy-safe dry-run unless `--execute` is provided. Its
output contains counts and fixed status codes only: no event IDs, aggregate
IDs, destinations, payloads, customer data or raw database errors.

After reviewing the dry-run, suppress the same bounded selection explicitly:

```bash
cd /opt/air-api
docker compose -f docker-compose.prod.yml exec -T app \
  python3 scripts/reconcile_installation_estimate_backlog.py \
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

## Production activation order

1. Deploy the managed worker dormant and prove one HA-fenced instance.
2. Set database runtime mode to `off`, fully stop the managed worker, and
   verify durable status `stopped`.
3. Run the backlog dry-run and the approved bounded suppression until the
   privacy-safe inventory reports zero and `activation_safe=true`.
4. Execute the existing operations Telegram canary and return mode to `off`.
5. Enable only the installation-estimate website scope.
6. Submit one new synthetic multipart request.
7. Verify one event, one delivery per active owner, provider acknowledgements
   and no duplicate after replaying the same `Idempotency-Key`.
8. On any anomaly, set database mode to `off`, disable the immutable gate and
   stop the worker.

Telegram does not offer provider-side idempotency. A lost acknowledgement after
Telegram accepted a message is therefore an ambiguous outcome, not a safe
automatic retry or proof of exactly-once delivery.
