# Service estimate money rollout

This change expands `service_estimate.subtotal/discount_amount/total`,
`service_estimate_item.line_total` and `order_service_link.price/cost` to
unconstrained PostgreSQL `NUMERIC`. It does not narrow the former integer range,
change product prices, backfill saved estimates or rewrite documents. Quantity
and tariff unit-price columns keep their existing precision and behavior.

For the schema-expansion release, first deploy [the integer/NUMERIC reader compatibility change](https://github.com/mvnby/air-api/pull/1035)
and verify its image revision on **both** API nodes. An older API process can
receive `Decimal` values from the new `NUMERIC` columns even when every saved
price is a whole ruble; disabling fractional writes alone does not protect it.
Run the normal CI migration test from an empty PostgreSQL test database. For
production, follow [production data operations](production-data-operations.md)
and the [deployment runbook](deployment.md). Before applying the migration, run
the following read-only queries against the current primary using the reviewed
connection path. Both result sets must be empty. The SQL works in the existing
image; it does not depend on the new script being deployed.

```sql
BEGIN READ ONLY;
SELECT e.id
FROM service_estimate e
LEFT JOIN (
  SELECT estimate_id, SUM(line_total) AS items_total
  FROM service_estimate_item GROUP BY estimate_id
) i ON i.estimate_id = e.id
WHERE ABS(e.subtotal::numeric - ROUND(e.subtotal::numeric, 2)) > 0.0000001
   OR ABS(e.discount_amount::numeric - ROUND(e.discount_amount::numeric, 2)) > 0.0000001
   OR ABS(e.total::numeric - ROUND(e.total::numeric, 2)) > 0.0000001
   OR e.subtotal < 0 OR e.discount_amount < 0 OR e.total < 0
   OR e.discount_amount > e.subtotal
   OR ABS((e.subtotal - e.discount_amount) - e.total) > 0.0000001
   OR ABS(e.subtotal - COALESCE(i.items_total, 0)) > 0.0000001
LIMIT 20;
SELECT id FROM service_estimate_item
WHERE line_total < 0
   OR ABS(line_total::numeric - ROUND(line_total::numeric, 2)) > 0.0000001
LIMIT 20;
ROLLBACK;
```

Review blockers separately; do not correct data as part of this release. The
migration repeats a stricter item-by-item check and stops before changing a
column. Once the new image is available, the equivalent read-only
`python3 scripts/report_service_estimate_money_preflight.py` runs inside it.

The first money rollout kept `EXACT_SERVICE_MONEY_WRITES_ENABLED=false` while
the new API and `NUMERIC` migration reached production. This follow-up release
changes the code default to `true`, allowing saved estimate cents to reach
orders without changing tariffs, product prices, or legacy checkout. **Do not
merge or deploy this follow-up** until both API nodes and communications workers
run the cent-aware #1034 image or newer, and the primary database reports
Alembic revision `e68b7c9d0e1f`. Confirm the active image revisions and the
usual `/api/health`, products, and filters smoke checks first.

An explicit `EXACT_SERVICE_MONEY_WRITES_ENABLED=false` environment value still
overrides the new default. It blocks fractional service writes but permits
whole-ruble writes and reads. This PR does not edit production environment
files; inspect the effective value on each runtime during the reviewed release.
Once cent rows exist, rollback must use a cent-aware image; do not downgrade
the migration to integer columns.

The old `Order.total_amount`, `total_cost` and `margin` columns are float-derived
caches. This package sums selected product/service lines in cents before writing
those caches; document tables derive their amounts from the frozen line prices
using `Decimal`. A later financial-ledger migration can retire float caches
without changing the line snapshot or historical documents.
