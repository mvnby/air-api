# Telegram communications canary

This is a bounded, idempotent operational event used to verify the durable
communications path. It is intentionally not a general-purpose message sender.
Each intentional run has an immutable, canonical lowercase UUIDv4 identifier.

Run from the repository root on the writable primary application node:

```bash
python3 -c 'import uuid; print(uuid.uuid4())'
python3 scripts/communications_telegram_canary.py --plan --run-id <uuid-v4>
python3 scripts/communications_telegram_canary.py --execute --run-id <uuid-v4>
python3 scripts/communications_telegram_canary.py --status --run-id <uuid-v4>
```

Every mode rejects a noncanonical run ID and fails closed unless these runtime
checks pass:

- `APP_ROLE` is exactly `primary`;
- PostgreSQL reports that it is primary and writable;
- a non-placeholder `BOT_TOKEN` is configured;

`--plan` and `--execute` additionally require:

- the database contains exactly two active owner `StaffUser` rows;
- both owners have positive Telegram user IDs.

`--execute` only commits the fixed
`ops.communications.telegram_canary.requested` outbox event. It never calls the
Telegram provider directly. The event and each materialized delivery have
`max_attempts=1`. Repeating `--execute` with the same run ID inspects the
existing run and never resurrects, requeues, or presents it as newly accepted.
The result distinguishes a new event, a pending replay, an ambiguous replay,
and terminal success, partial delivery, or failure. A different UUIDv4 creates
an independent event; old event and delivery rows are retained as history.

The recipient snapshot contains only stable `staff:<id>` keys. The CLI never
prints Telegram destinations, names, payloads, rendered content, raw provider
acknowledgements, tokens, connection details, or error messages. `--status`
reports only safe IDs, states, attempt counters, a provider-ack boolean, error
codes, and timestamps.

`--status` reads the exact historical run and does not require its former owner
pair to remain active. This preserves auditability after staffing changes.

There are deliberately no CLI flags for destination, recipient, message text,
retry count, priority, template selection, or arbitrary run label.
