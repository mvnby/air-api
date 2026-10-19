# Biocond source catalog repair

This operation covers the reviewed MDV (brand 1), TCL (brand 3), and Mitsubishi
Heavy Industries (brand 14) catalog. It fills missing series and source links,
corrects reviewed specifications and prose, and adds explicit feature links.
It never changes product titles, prices, media, SEO, product kind, or ownership.
It never deletes catalog objects or replaces complete feature sets.

Follow [production data operations](production-data-operations.md) and deploy
from the exact reviewed image. Source conflicts must be resolved in the checked-in
manifest before planning. A plan is a read-only report, not execution permission.

The user confirmed that MHI SRK-ZTL-W keeps the manufacturer limit of -15°C
for heating and that its additional fine filters are optional. Do not add a
-20°C claim or bundled fine-filter assignment to that series.

## Manifest contract

The reviewed manifest is
`config/catalog_source_repairs/biocond-2026.json`, schema version 1. Lists of all
existing product and series IDs for the three brands are frozen in `scope`.
Every product appears once, including products with no edits. A newly discovered
product, series, changed identity, or unknown feature link blocks execution.

Top-level keys:

| Key | Contract |
| --- | --- |
| `schema_version` | Integer `1` |
| `scope` | `brand_ids: [1,3,14]`, complete `product_ids`, complete original `series_ids` |
| `sources` | Reviewed source URLs, hashes and page/model locators |
| `brands` | Exact `{id,slug,title}` identity, `before_sha256`, `fields_set`; only fill an empty `official_url` |
| `products` | Exact `{id,brand_id,slug,title}` identity and projections described below |
| `series` | Exact `{id,brand_id,slug}` identity, `before_sha256`, `fields_set` limited to title/description/short_description/source_url/features |
| `new_series` | Unique `key`, exact `{brand_id,slug}` identity, `before: {present:false}`, reviewed `fields_set` |
| `new_features` | Unique `key`, exact `{brand_id,slug}` identity, `before: {present:false}`, reviewed active brand-scoped feature fields and source provenance |
| `documents` | Exact `{brand_id,url}` identity, `before: {present:false}`, document metadata with `source_url` |
| `manual_links_before` | All existing brand/series/product feature links, including inherited/derived links, as canonical full projections |
| `feature_links` | Explicit series/product link upserts; omitted links remain untouched |

The optional series `features` field is the legacy prose array, not feature-link
rows. It may contain at most100 strings of at most2000 characters each. Exact
before hashes guard reviewed corrections to contradictory legacy claims; content
blocks and media remain outside this operation.

New records are found by natural identity on a repeated run. They must equal the
complete reviewed target, including default fields; an unrelated record with the
same slug or a manually modified created record blocks the operation. Original
series IDs remain frozen; only these exact new series are accepted on reruns.

A product row contains:

```json
{
  "identity": {"id": 779, "brand_id": 14, "slug": "exact-current-slug", "title": "Exact current title"},
  "specs_set": {"capacity_heating_kw": "3.0"},
  "specs_delete": [],
  "rebuild_typed": ["capacity_heating_kw"],
  "fields_set": {"description": "Reviewed prose", "series_assignment_source": "manual"},
  "series_key": "mhi-ztl-w",
  "before": {
    "specs": {},
    "typed": {},
    "filters": {},
    "fields_sha256": {}
  },
  "source_before_sha256": "HASH_OF_COMPLETE_BEFORE_PROJECTION"
}
```

The empty projection objects above are structural placeholders: a real manifest
must contain every guard returned by `spec_families(row)`. Use the exported
helpers in `services/catalog_biocond_source_repair.py` to build guards:

```python
keys, filters = spec_families(row)
specs = product.specs or {}
row['before'] = {
    'specs': {key: present(specs, key) for key in keys},
    'typed': {key: present(specs.get('__typed_specs', {}), key) for key in keys},
    'filters': {key: present(specs, key) for key in filters},
    'fields_sha256': {
        key: digest(getattr(product, key)) for key in row['fields_set']
    },
}
row['before']['fields_sha256']['series_ref'] = digest(
    f'id:{product.series_id}' if product.series_id is not None else None
)
row['source_before_sha256'] = digest(row['before'])
```

Each presence guard is `{"present":false}` or
`{"present":true,"value":<exact original JSON>}`. Null and absent are distinct.
Every product guards its original series reference, including untouched products.
`series_key` may name a new symbolic series key or an existing `id:123`. When an
assignment is requested, set and guard `series_assignment_source: "manual"`.

A cooling-capacity correction also requires a matching `power_cooling` field
change and its before hash. Nominal capacity and power-consumption families
include their raw minimum/maximum companions when rebuilding the typed nominal
payload. Untouched companion raw strings, unrelated typed payloads, and unrelated
filter keys are preserved. Wi-Fi raw/typed/filter keys are rebuilt together.

Build `manual_links_before` using `link_projection(link, kind)`, where `kind` is
`brand`, `series`, or `product`. The result keeps the link ID, all durable flags,
media overrides, prose, and source; only timestamps are omitted:

```json
{
  "id": 50,
  "kind": "product",
  "target": "id:779",
  "feature": "id:86",
  "fields": {"source": "manual", "is_enabled": true}
}
```

The `fields` object above is abbreviated for readability. Real guards must use
all fields returned by the helper, including null overrides. A link operation is:

```json
{
  "kind": "series",
  "target": {"series_key": "mhi-ztl-w"},
  "feature": {"feature_key": "mhi-3d-auto"},
  "before": {"present": false},
  "fields_set": {
    "source": "manual",
    "is_enabled": true,
    "is_featured": true,
    "display_mode": "detailed",
    "override_footnote": "Reviewed source and precise scope"
  }
}
```

Existing targets/features use `{"id":123}`. Existing link `before.value` is the
exact full original `fields` object. False exclusions use `is_enabled:false`;
they are retained as rows. Derived or inactive features cannot receive a new
manual assignment. Brand-scoped features cannot cross brands. Link media is
never changed by this tool. New link sequence IDs are represented by deterministic
semantic keys only in the post-repair comparison; existing IDs remain guarded.

## Plan and execution

Generate and save the complete plan from the deployed reviewed image:

```bash
python3 scripts/repair_biocond_catalog.py --manifest config/catalog_source_repairs/biocond-2026.json > /tmp/biocond-plan.json
```

Review every source, identity, before/target hash, operation, affected product,
and brand/series invalidation path. Execute only with that full JSON and its exact
`plan_digest`, within 30 minutes:

```bash
python3 scripts/repair_biocond_catalog.py --manifest config/catalog_source_repairs/biocond-2026.json --execute --reviewed-plan /tmp/biocond-plan.json --execute-plan-digest REVIEWED_SHA256
```

Planning uses a repeatable-read read-only transaction. Execution positively
verifies the primary, takes a stable advisory/parent/link lock order, regenerates
the complete live plan, and rejects any manifest or scoped-state drift. Business
rows, one global revision, and one invalidation outbox event commit together.
Any failure rolls all of them back. A fresh plan after success has `changed:0`;
executing that plan performs no writes and stages no revision/event.

## Verification

Run the meaningful pure guards and real PostgreSQL CLI integration test:

```bash
python3 -m pytest tests/unit/test_biocond_source_repair.py tests/integration/test_biocond_catalog_source_repair.py -q
```

The [backend test procedure](development-workflow.md#backend-tests) requires a
separate physical database per pytest process. The integration test verifies a
failure after actual revision/outbox staging, successful atomic creation and
correction, preserved unrelated fields, all affected paths, and a repeated no-op.
After authorized production execution, inspect the fresh plan, exact targeted
specifications, series assignments, feature exclusions, source documents, and
invalidation delivery before claiming completion.
