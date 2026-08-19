# Product media URL backfill

This runbook repairs product image references that are outside the strict
storefront media allowlist. It is deliberately separate from widening the web
allowlist: only exact immutable URLs under `https://cdn.mvn.by/products/shared/`
or `https://cdn.mvn.by/products/variants/original/` are accepted.

## Safety contract

- `audit` and `plan` are read-only; `plan` is the CLI default.
- `execute` requires the exact signed token from a fresh ready plan and runs
  only on a writable PostgreSQL primary.
- One transaction-scoped advisory lock serializes execution.
- The manifest pins the canonical public catalog count/hash and the published
  database `id + slug + main_image` hash. Source/product membership is exact.
- Every changed `Product`, `Product.images`, `ProductImage`, and
  `ProductImageVariant.url` value must still equal the reviewed old value.
- Source downloads use HTTPS, exact host allowlists, public-IP DNS checks,
  bounded redirects, 15-second requests, a 20 MiB limit, an image MIME
  allowlist, actual image decoding, and a 70-megapixel cap.
- New originals go through `ProductOriginalMediaService` and the configured
  content-addressed product-original storage. The command does not perform raw
  bucket writes.
- The database changes and catalog invalidation/outbox event are staged in the
  same caller transaction. Storage objects are immutable and may be safely
  reused; the command never deletes media.
- Supplier mappings, cost, prices, offers, grants, and publication state are
  outside this command's mutation surface.

## Polotsk presentation snapshot

Manifest:
`config/product_media_url_backfills/polotsk-presentation-v1.json`

The reviewed snapshot contains 1,235 public products. Exactly 46 products have
138 rejected `main_image`/`card_image`/`full_image` fields across 15 unique
sources:

- 23 products use seven legacy URLs whose exact bytes already exist under an
  allowed immutable `products/variants/original` URL;
- 20 products use seven MVN-owned sources that can be ingested through the
  shared original-media pipeline;
- three LG products remain explicitly blocked with
  `external_rights_review_required`.

The executable subset is therefore exactly 43 products. The three acknowledged
LG residuals are carried in the signed plan digest but excluded from mutation
locations. `executable_complete=true` means the 43 reviewed products are
repaired; `presentation_complete=false` remains explicit while the three LG
cards continue to use the branded local placeholder.

The blocked LG rule is intentional. Do not change it to `ingest` until the
operator has a concrete rights-review reference; an external ingest rule also
requires an exact source/redirect host allowlist.

## Read-only checks

Run from the deployed API image on the current primary:

```bash
python3 scripts/manage_product_media_url_backfill.py audit \
  --manifest config/product_media_url_backfills/polotsk-presentation-v1.json
```

The audit must report:

- `product_count=1235`;
- `snapshot_matches=true`;
- `blocked_product_count=46`;
- `blocked_field_count=138`;
- no unmatched blocked URLs or source/product drift.

Build the database-aware plan:

```bash
python3 scripts/manage_product_media_url_backfill.py plan \
  --manifest config/product_media_url_backfills/polotsk-presentation-v1.json
```

The plan may be `ready=true` for the exact 43-product executable subset while
reporting `deferred_product_count=3` and `presentation_complete=false`. This is
not permission to ingest LG media: those rows remain unchanged and are not
included in the execute location list.

## Reviewed execution after all blockers are resolved

1. Run a fresh `audit` and `plan` on the PostgreSQL primary.
2. Review counts, every source target/hash, the exact location list, the absence
   of unexpected blockers, and the exact three-product LG deferred set.
3. Capture the JSON plan as the change evidence in a root-only operations log.
4. Run only the emitted `reviewed_execute_command` before its 15-minute token
   expires. Do not hand-edit the token or command.
5. Capture the execute JSON, including `execution_id`, plan digest, content
   hashes, changed products, and changed locations.
6. The command performs a bounded post-commit public verification. It must show
   exactly three residual products / nine fields, all on the acknowledged LG
   source, and no other blocked URL. Re-running a fresh plan/execute must be an
   idempotent no-op for the 43-product executable subset.
7. Verify `/api/health`, `/api/ready`, the public catalog, and a sample of each
   resulting CDN URL before considering the operation complete.

If the public or database snapshot changes, if a source redirects outside its
allowlist, if content changes between plan and execute, or if the host is a
standby, stop and produce a new reviewed plan. Never reuse a stale token.
