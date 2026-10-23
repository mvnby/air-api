# Catalog electrical supply repair

This manual correction fills source-supported electrical supply information for
63 products, enriches 16 existing TCL entries and corrects three Energolux
voltage conflicts. Follow the
[production data gates](production-data-operations.md) and run the released
immutable backend image on the positively verified PostgreSQL primary. The
operation never runs automatically during deployment.

The 2026-10-23 read-only inventory checked all 1,241 catalog products for power
fields and selected 310 semicommercial systems and relevant indoor units by
system type, indoor form or industrial category. Mobile floor-standing units
were excluded. Of these 310 records, 247 already contained electrical data and
63 had none: 27 Energolux, 19 KINGHOME, 16 Hisense and one TCL. All 63 missing
records now have exact-model source evidence in the manifest. Existing data
outside the source-reviewed corrections is retained, not independently
recertified. Legacy raw field names are supported by the proposal formatter.

The [manifest](../config/catalog_source_repairs/power-supply-2026-10.json) contains
82 exact product identities, the complete reviewed raw/typed power-family before
state and official source URLs, hashes and page/model locators. Its canonical
JSON digest is pinned in the helper; editing a source or assignment requires a
new reviewed release. The repair changes only the five canonical `power_supply*`
keys, their reviewed typed counterparts and explicitly listed legacy aliases.
Prices, models, product kinds, type tags, media, other specifications, supplier
data and tenant grants are preserved.

Indoor and outdoor supply are kept separate. Eight TCL systems have a single
phase 220-240 V indoor unit and a three phase 380-415 V outdoor unit; their old
generic 220-240 V field hid the outdoor requirement. The manifest preserves both
values and removes the conflicting legacy voltage alias. The catalogue does not
prove the TCL mains connection point, so that field remains absent. KINGHOME
provides a system supply row and an explicitly labelled outdoor mains cable;
separate indoor voltage is not assumed. Energolux connection points and Hisense
indoor/outdoor requirements use their exact model tables.

Energolux CABINET 6 products 520, 555 and 558 had contradictory values: their
general supply stated 220-240 V while the voltage field stated 380-415 V.
Exact base, WS30 and WS40 distributor pages directly link the same manual, whose
page 17 specifies 220-240 V / 50 Hz / 1 phase for the 24 model pair. Only the
voltage field and its typed value are corrected; the supported general supply
and connection location are preserved. The source conflict and variant
applicability evidence remain in each manifest row.

KINGHOME product 97 has a catalogue conflict: its floor/ceiling table prints
`3/220-415/50`. The official brand page for the exact indoor/outdoor pair states
`1/220-240/50`, corroborated by two catalogue tables using the same exact outdoor
model. All conflict evidence is retained in that manifest row. TCL TUB-18HRA
(184) needs no voltage correction: its existing 220-240 V value agrees with the
[official distributor's exact-model page](https://tcl-russia.ru/product/polupromyshlennye-konditsionery/neinvertornye-on-off/napolno-potolochnye-split-sistemy/napolno-potolochnyy-konditsioner-5-30-kvt/),
which states 220-240 V / 50 Hz / 1 phase. It is outside the mutation manifest.

## Plan and execute

From the released application's working directory, save the complete read-only
repeatable-read plan:

```bash
python3 scripts/repair_catalog_power_supply.py > /tmp/power-supply-reviewed.json
```

Review every identity, raw/typed before and target state, assignment, deletion,
source, changed count and digest. Retain the before plan outside the repository
for an independently reviewed rollback if needed. Never edit a saved plan to
bypass a blocker.

Within 30 minutes, execute only that full plan and its exact digest:

```bash
python3 scripts/repair_catalog_power_supply.py --execute \
  --reviewed-plan /tmp/power-supply-reviewed.json \
  --execute-plan-digest REVIEWED_PLAN_DIGEST
```

Execution verifies the primary, locks reviewed brands and products in stable ID
order with a five-second lock timeout, and replans in the same transaction. A
missing identity, changed model/source, new or removed power alias, typed drift,
partial application, expired plan or mismatched digest aborts the operation.
The complete family is guarded, including unexpected `power_supply*` keys;
unrelated concurrent edits are retained. Whole-product normalization is never
used. Only changed electrical typed families are rebuilt through the registry.

Business edits and one global catalog revision/outbox invalidation are committed
atomically through `CatalogInvalidationCommitService.commit_global_mutation`,
with reason `catalog_power_supply_repair`. A failure rolls back both business
changes and invalidation. A fresh plan after success must report `changed=0`;
executing that reviewed zero-change plan performs no writes or new revision.

Verify changed public product specifications, Manager order equipment
descriptions and delivery of the invalidation event before claiming completion.
Existing saved business documents are not regenerated by this operation.

## Local checks

Use an isolated physical PostgreSQL test database per process as described in
the [test procedure](development-workflow.md#backend-tests).

```bash
pytest tests/unit/test_catalog_power_supply_repair.py \
  tests/integration/test_catalog_power_supply_repair_postgres.py -q
python3 scripts/repair_catalog_power_supply.py --help
```

The integration test exercises the actual CLI transaction, refusal of added
aliases, preservation of unrelated edits, rollback after real revision/outbox
staging, one successful commit, stale-plan refusal and a zero-write repeat.
