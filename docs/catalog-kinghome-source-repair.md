# KingHome 2026 source repair

This manual operation corrects the reviewed KingHome import discrepancies.
Follow the [production data gates](production-data-operations.md) and use the
released immutable backend image on the verified primary. The script does not
run during deployment. Start with a read-only plan.

The checked-in [manifest](../config/catalog_source_repairs/kinghome-2026.json)
contains 42 exact product identities and nine series identities. Changes are
limited to 36 products and seven series: 124 raw specification assignments,
four unconfirmed Nordic ionizer removals, 26 airflow typed-value repairs,
23 product summaries and seven series' short/full descriptions. The original
long descriptions are guarded by hashes; prices and secrets are absent.

The authoritative technical source is the official 2026 catalog with SHA256
`d5bc15c528624cfcc6ad3660abcb7d4ac7b1c3b4d54a0c4a250b1bf6b5c41054`, plus the
official supplier sheet referenced by the manifest. Printed page n is PDF
page n+1. Product 1309's width 1400, height 300 and depth 700 mm additionally
use the user's explicit 2026-10-19 orientation confirmation for KUD160PHS1/A-S.
The user also confirmed cassette heights: KUD71T1/A-S (1301) is 200 mm
(printed page 66), and KUD140T1/A-S (1304) is 290 mm (printed page 68);
both retain width/depth 840/840 mm. The other 20 field comparisons are
axis no-ops: cassette dimension ordering or an alternative floor/ceiling
mounting orientation. They require no swaps; no dimension questions remain open.

Nordic ionization is unknown: the catalog narrative conflicts with the model
feature table/supplier evidence and the user selected conservative claims.
Removing that raw key and its typed counterpart does not assert physical
absence. U-Match Wi-Fi is conditional on XE7A-24/HC or XE7C-24/HC; canonical
`wifi_ready="ready"`, `wifi_state="ready"`, `wifi_builtin=false` and their filter
and typed counterparts are rebuilt consistently. Controller inclusion is not
promised. Old PS1 website tables are not a substitute for exact PHS1 matching.

## Plan, review, execute

Run from the backend image's application directory. The default command uses
the checked-in manifest and a read-only repeatable-read transaction:

```bash
python3 scripts/repair_kinghome_catalog.py > /tmp/kinghome-reviewed-plan.json
```

Review the complete JSON: exact product/series scope, before/target fields,
proposed descriptions, `manifest_sha256`, `changed` and `plan_digest`. Retain
the read-only before snapshot outside the repository for an independently
reviewed rollback if needed. A blocked or partially changed state is not
executable. Do not edit a saved plan to bypass a blocker.

Within 30 minutes, pass the saved JSON and its exact reviewed digest:

```bash
python3 scripts/repair_kinghome_catalog.py --execute \
  --reviewed-plan /tmp/kinghome-reviewed-plan.json \
  --execute-plan-digest REVIEWED_PLAN_DIGEST
```

Execution verifies the PostgreSQL primary, locks brand/products/series in stable
ID order with a five-second lock timeout, and checks every scoped identity and
reviewed field again, including unchanged/already-correct rows. A stale digest,
changed manifest, expired plan, unknown value or partial repair aborts the whole
operation. Unrelated values are preserved. Only reviewed raw/typed/filter
families are rebuilt; the entire product is never normalized.

All business edits and a single revision/outbox invalidation use one transaction
through `CatalogInvalidationCommitService.commit_global_mutation`, with reason
`kinghome_source_catalog_repair`. Invalidation includes all 42 KingHome products,
the brand and all nine `/brands/kinghome/series/<slug>/` pages.

Generate a fresh plan after execution; it must report `changed=0`. A reviewed
zero-change execution performs no revision/outbox write. Verify corrected public
cards, series descriptions, filters and the outbox delivery before reporting
completion. The tool does not alter prices, product kinds, model names, media,
feature links or SEO.

## Local verification

The pure planner/normalizer tests need no database. Use the repository's
configured test environment; PostgreSQL tests must use the separately isolated
test databases described in the [test procedure](development-workflow.md#backend-tests).

```bash
pytest tests/unit/test_kinghome_source_repair.py \
  tests/unit/test_catalog_invalidation_commit_service.py \
  tests/unit/test_spec_normalizer_filters.py -q
python3 scripts/repair_kinghome_catalog.py --help
```
