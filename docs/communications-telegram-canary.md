# Telegram communications canary

This is a bounded, idempotent operational event used to verify the durable
communications path. It is intentionally not a general-purpose message sender.
Each intentional run has an immutable, canonical lowercase UUIDv4 identifier.

Do not execute a live canary merely because this script exists. Before the
first production run, deploy one release consistently across API/migration and
the communications worker, verify Alembic revision `6c0d3e5f7a21`, prove the
worker owns the writable-primary advisory lock, keep
`COMMUNICATIONS_WORKER_ALLOW_ALL_MODE=false`, and confirm there is no older
worker process. This follow-up has not itself performed a production deploy or
live Telegram send.

Run from the repository root on the writable primary application node:

```bash
python3 -c 'import uuid; print(uuid.uuid4())'
python3 scripts/communications_telegram_canary.py --plan --run-id <uuid-v4>
python3 scripts/communications_telegram_canary.py --execute --run-id <uuid-v4>
python3 scripts/communications_telegram_canary.py --status --run-id <uuid-v4>
python3 scripts/communications_telegram_canary.py --off
```

`--plan`, `--execute`, and `--status` reject a noncanonical run ID and fail
closed unless these runtime checks pass:

- `APP_ROLE` is exactly `primary`;
- PostgreSQL reports that it is primary and writable;
- a non-placeholder `BOT_TOKEN` is configured;

`--plan` and `--execute` additionally require:

- the database contains exactly two active owner `StaffUser` rows;
- both owners have positive Telegram user IDs.

`--execute` atomically commits the fixed
`ops.communications.telegram_canary.requested` outbox event and arms the durable
runtime control for that exact run. It never calls the Telegram provider
directly. The event and each materialized delivery have `max_attempts=1`.
The runtime scope contains an explicit event/template allowlist, the
deterministic event ID, the canonical run ID, and a monotonically increasing
control revision. Dispatcher selection, delivery claim, expired-lease recovery,
and every network-action fence all use that same immutable scope.

Repeating `--execute` with the same run ID inspects the existing run and never
re-arms the runtime, resurrects, requeues, or presents it as newly accepted.
The result distinguishes a new event, a pending replay, an ambiguous replay,
and terminal success, partial delivery, or failure. Before executing a different
UUIDv4, explicitly switch the current scope off. Old event and delivery rows are
retained as history.

`--off` is the emergency stop path. It deliberately takes no run ID and does
not depend on `BOT_TOKEN`, the current owner pair, or historical canary data. It
still requires `APP_ROLE=primary` and a writable primary PostgreSQL transaction.
Repeated `--off` is idempotent. A real mode/scope transition increments the
control revision, so a worker holding an older scope cannot resume after a fast
`canary A -> off -> canary A` flip.

Direct `canary -> all`, `all -> canary`, and `canary A -> canary B` transitions
are rejected; every scope change must pass through `off`. There is deliberately
no CLI `--all` switch. Full website-event delivery additionally requires the
immutable deployment setting `COMMUNICATIONS_WORKER_ALLOW_ALL_MODE=true`; its
default is `false`, and canary processing remains available while it is false.

The recipient snapshot contains only stable `staff:<id>` keys. The CLI never
prints Telegram destinations, names, payloads, rendered content, raw provider
acknowledgements, tokens, connection details, or error messages. `--status`
reports only safe IDs, states, attempt counters, a provider-ack boolean, error
codes, and timestamps.

`--status` reads the exact historical run and does not require its former owner
pair to remain active. This preserves auditability after staffing changes.

There are deliberately no CLI flags for destination, recipient, message text,
retry count, priority, template selection, or arbitrary run label.
