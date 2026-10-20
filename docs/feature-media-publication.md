# Reviewed feature media publication

This manual operation replaces only the reviewed feature visuals: 35 semantic
icons and 13 large illustrations from the TCL/MDV/MHI audit. It changes only
`Feature.icon_media_id`, `Feature.image_media_id` and `Feature.image_url`.
The legacy `icon` string is preserved. Feature ownership, assignments, rules,
descriptions, priorities, product specifications and product media are untouched.

Unlike ordinary Manager feature editing, this media-only operation accepts
the frozen `derived` features 40, 73 and 84. Their identities and all media
guards must still match. It does not migrate these features or change their
resolution semantics.

Start with [production data operations](production-data-operations.md). Run from
the exact reviewed deployed image under the production deployment lock, using
the currently verified PostgreSQL primary. This procedure does not authorize
uploading files or executing a production mutation by itself.

## Manifest and plan

Upload reviewed originals through the existing media library first. Each target
must already exist as a ready, global `kind=feature`, `variant_type=original`
asset with no parent, tenant or storefront. There is no download, upload, media
file read or storage mutation in the publication command. It verifies each exact
ID, URL and SHA-256 against the media row and canonical library storage URL;
external hosts and arbitrary paths cannot be introduced.

Supply a private JSON manifest with `schema_version: 1` and `features` containing
the exact 35 reviewed IDs. Every row has the following shape (the illustration
target is required only for the exact 13 illustration IDs):

```json
{
  "identity": {"id": 19, "slug": "pamiat-polozheniia-zhaliuzi", "scope_type": "universal", "brand_id": null},
  "before": {"icon": "reviewed old value", "icon_media_id": null, "image_url": "reviewed old URL or null", "image_media_id": null},
  "target": {
    "icon": {"id": 10019, "url": "/media/library/original/EXACT_HASH.svg", "content_hash": "EXACT_64_LOWERCASE_HEX"},
    "image": {"id": 20019, "url": "/media/library/original/EXACT_HASH.webp", "content_hash": "EXACT_64_LOWERCASE_HEX"}
  }
}
```

The IDs, values and hashes above are placeholders, not executable data. Snapshot
all four `before` media fields, including nulls, from a fresh read. There are no
local asset paths in the manifest. Unknown fields, duplicate JSON keys, duplicate
feature identities, missing guards and scope expansion fail closed. The exact
ID sets live beside the validator in
[feature media publication](../services/feature_media_publication.py).

```bash
python3 scripts/publish_feature_media.py --manifest /tmp/feature-media-manifest.json > /tmp/feature-media-reviewed.json
```

The default command uses a read-only repeatable-read transaction and rolls it
back. Review the complete `observed` before/after guards, exact `operations`,
asset identities and `affected_scope`, then retain that JSON and its
`plan_digest`. This operation deliberately invalidates the full global catalog:
universal features can affect brands beyond the three audited brands. The plan
lists all product IDs/slugs, brand slugs and series page paths in that scope.

## Execute and verify

Within 30 minutes, run the exact manifest and reviewed JSON with its digest:

```bash
python3 scripts/publish_feature_media.py --manifest /tmp/feature-media-manifest.json --execute --reviewed-plan /tmp/feature-media-reviewed.json --execute-plan-digest EXACT_REVIEWED_PLAN_DIGEST
```

Execution positively verifies PostgreSQL primary status, takes a transaction
advisory lock and locks the feature and target media rows in stable ID order.
It recomputes the plan and requires the same exact reviewed state and digest.
Each feature must match either all four original media guards or its complete
target. Partial application or drift blocks the transaction. A stale review
cannot be reused after another application; generate and review a fresh plan.

Feature changes, the global revision and all storefront invalidation events
commit together through `CatalogInvalidationCommitService`. A no-op rolls back
without a revision or event. Failures roll back all changes; inspect the cause
and generate a fresh plan before retrying. There is no automatic reversal or
asset deletion. Reversal requires a separately reviewed operation preserving
the previous media references recorded in the plan.

After execution, generate a fresh plan and require `changed=0`. Verify the
feature media fields, unchanged assignments/rules, catalog revision and pending
invalidation delivery. Check public feature cards on products using universal
features outside TCL/MDV/MHI as well as the audited products, and confirm
`/api/health`, `/api/v1/products?limit=5` and `/api/v1/filters/config`.
