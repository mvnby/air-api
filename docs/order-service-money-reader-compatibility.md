# Order service money reader compatibility

The future service-money migration changes `order_service_link.price/cost` from
PostgreSQL `INTEGER` to `NUMERIC`. PostgreSQL then returns `Decimal` values even
for whole-ruble rows. The previous API calculated order totals by adding those
values to float installer costs, which raises `TypeError` during a rolling
deployment. This release makes the existing reader accept either type. It does
not change the schema or allow fractional service writes.

Release this change first. Follow [deployment](deployment.md) and [API HA](api-ha-runbook.md)
through their normal checks, and verify the new image revision on both API nodes
before applying the separate service-money migration. The PostgreSQL integration
test covers both the current `INTEGER` columns and transactional `NUMERIC`
columns while this reader's model still declares integers.

Only then run the later migration's read-only production preflight and release
that migration with fractional writes disabled. Keep fractional writes disabled
until both API nodes run the cent-aware implementation. Rolling back the schema
after cent rows exist would discard information; use a cent-aware image instead.
