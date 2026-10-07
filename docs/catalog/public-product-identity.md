# Public product identity

Public catalog/detail, search, series pages and sibling/navigation DTOs expose
nullable string fields `model_code` and `capacity_class`. Titles, slugs, public
URLs and SEO fields keep their existing meaning.

The shared catalog specs JSON is the canonical storage; no duplicate product
columns or database migration are needed:

- `specs.model` is the exact manufacturer designation. The existing `Модель`
  source alias and `model_code` normalize to this same key. Indoor/outdoor model
  identifiers and supplier SKUs are separate specs and are not substitutes.
- `specs.capacity_class` is an explicitly confirmed nominal class. Source aliases
  `Номинальный класс мощности` and `Класс мощности` normalize through the shared
  registry/normalizer. A positive integer class of one or two digits is formatted
  with at least two digits (`9` becomes `09`). Measured BTU/h or kW values,
  ranges, booleans and malformed values do not confirm a class.

The public mapper reads only canonical keys. Missing/invalid values return
`null`; it never extracts either field from title or infers a class from cooling
power, floor area or digits in the model designation. Existing structured models
are available immediately. Existing records lacking a confirmed nominal class
remain `null`, including a model with `09` in its designation.

For example, structured source data `Модель: KWH09ACC-S6DBA2A` and
`Класс мощности: 9` normalize to `model: KWH09ACC-S6DBA2A` and
`capacity_class: 09`; the API exposes `model_code: KWH09ACC-S6DBA2A` and
`capacity_class: 09`. These are input examples, not evidence of populated
production records.

New imports and reviewed catalog edits use the existing
[spec normalization workflow](../development-workflow.md#2-specs-normalization-workflow-newupdated-keys).
A production transfer for old records requires verified structured source data
and the review gates in [production data operations](../production-data-operations.md).
This contract release does not run a production backfill or a title-based migration.
