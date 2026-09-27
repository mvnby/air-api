# Complete-split selection data audit

Read-only public catalog snapshot: 2026-09-27 12:45 UTC. The source is paged
`GET https://api.mvn.by/api/v1/catalog?tag_slugs=cat-industrial&limit=100` and
the analogous `cat-multi` query, plus all 13 pages of the unfiltered catalog.
The full published snapshot has 1,239 products: 708 persisted
`complete_split_system`, 138 `indoor_unit`, 46 `outdoor_unit`, 244 `other` and
103 `unknown`. The new selection scope admits the 708 complete products and
excludes the other 531; none of the 708 has a contradictory multi type/category
in this snapshot. These are published products only; Manager
drafts, production database rows and source-of-kind provenance were not exposed.
No production data was changed.

| Category | Published | `complete_split_system` | `other` | `unknown` | `indoor_unit` | `outdoor_unit` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Semi-industrial | 258 | 22 | 223 | 13 | 0 | 0 |
| Multi-split | 186 | 0 | 1 | 1 | 138 | 46 |

In the semi-industrial category, 237 products have
`specs.type=полупромышленный кондиционер` and 21 have `сплит-система`.
Nineteen `other`/`unknown` records have both canonical component flags set to
true and `indoor_units_count=1`. They are the only source-backed legacy
classification candidates found in this snapshot:

- `unknown`: 1297–1309 (13 KINGHOME cassette/duct products).
- `other`: 94–99 (6 KINGHOME floor-ceiling products).

Another 194 `other`/`unknown` products have indoor/outdoor model references but
lack both canonical component flags. A model pair, title, form, capacity or
category alone is not enough to assert a complete sellable system. They remain
outside selection pending source review. The 22 already-complete products do
not need component flags to remain eligible. The selected-product predicate
also vetoes contradictory `type` and `cat-multi` data.

Future classification of a semi-industrial product with both explicit component
flags now yields `complete_split_system`. Persisted `other` is not silently
overwritten because the schema cannot distinguish an old automatic result from
a manager's manual kind choice. The 13 persisted `unknown` and 6 persisted
`other` candidates therefore need an exact, reviewed data correction before
this strict scope can be released without losing them. Prepare a separate
report-only plan from the current database and source documents, then review
each ID and any manual choice before mutation. Do not infer a repair from this
public snapshot or run a production backfill as part of the code PR.
