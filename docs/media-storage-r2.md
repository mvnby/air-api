# Product Media Storage: R2/S3 Migration

This project keeps legacy local product image URLs working while moving new
runtime media writes to public S3-compatible object storage such as Cloudflare
R2.

## URL Strategy

- Existing `ProductImage.url`, `Product.main_image`, and legacy
  `Product.images` values may remain local `/media/...` URLs until migrated or
  intentionally retained.
- Manager uploads and search/download attaches write source originals through
  `PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER`, then write/update
  `ProductImageVariant(variant_type=original)` through
  `PRODUCT_MEDIA_STORAGE_PROVIDER`.
- Import media downloads also use the original source storage adapter. In
  production this should be `r2`, so new importer/cache URLs are CDN URLs
  instead of new local `/media/products/shared/...` files.
- Generated rows in `ProductImageVariant`, plus new manager-uploaded
  `original` variant rows, can use `storage_provider=r2` (or
  `s3`/`s3_compatible`) and public CDN URLs.
- The public API still falls back to the original URL when an approved ready
  variant is absent, so legacy local media remains a rollback path.
- The first rollout uses stable public URLs from `PRODUCT_MEDIA_S3_PUBLIC_BASE_URL`.
  Signed URLs and API proxying are intentionally out of scope for product
  catalog images because storefront rendering needs cacheable public assets.

## Cache And Versioning

Objects are stored with content-addressed keys:

```text
{PRODUCT_MEDIA_S3_KEY_PREFIX}/{variant_type}/{sha256}.{extension}
```

Local `original` variant targets intentionally stay compatible with the shared
source URL shape:

```text
/media/products/shared/{sha256}.webp
```

With an R2/S3 provider, an `original` variant uses the same content-addressed
variant key pattern as other variants:

```text
{PRODUCT_MEDIA_S3_KEY_PREFIX}/original/{sha256}.webp
```

The default cache header is:

```text
public, max-age=31536000, immutable
```

When a variant is regenerated and bytes change, the SHA-256 changes, the object
key changes, and the database URL changes. CDN caches can keep old objects
without serving stale images from current product responses. If bytes are
identical, reusing the same key is safe.

## Environment

Local fallback is the default:

```dotenv
PRODUCT_MEDIA_STORAGE_PROVIDER=local
PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER=local
MEDIA_STORAGE_PROVIDER=local
```

Cloudflare R2 example:

```dotenv
PRODUCT_MEDIA_STORAGE_PROVIDER=r2
PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER=r2
PRODUCT_MEDIA_S3_BUCKET=mvn-product-media
PRODUCT_MEDIA_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
PRODUCT_MEDIA_S3_REGION=auto
PRODUCT_MEDIA_S3_ACCESS_KEY_ID=<secret>
PRODUCT_MEDIA_S3_SECRET_ACCESS_KEY=<secret>
PRODUCT_MEDIA_S3_PUBLIC_BASE_URL=https://cdn.mvn.by/media
PRODUCT_MEDIA_S3_KEY_PREFIX=products/variants
PRODUCT_MEDIA_ORIGINAL_S3_KEY_PREFIX=products/shared
PRODUCT_MEDIA_S3_CACHE_CONTROL=public, max-age=31536000, immutable

# Shared non-product media: articles, media library, order/bot attachments.
# Empty MEDIA_S3_* values reuse PRODUCT_MEDIA_S3_* values.
MEDIA_STORAGE_PROVIDER=r2
MEDIA_S3_KEY_PREFIX=
```

Dry-run migration requires bucket, endpoint, public base URL, and key prefix so
it can print target keys. Secret access keys are only required for writes.

Product original source files may remain local during a cautious rollout, but
production should switch them to R2 once CDN reads are verified:

```dotenv
PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER=local
PRODUCT_MEDIA_LOCAL_ORIGINAL_DIR=media/products/shared
PRODUCT_MEDIA_LOCAL_ORIGINAL_PUBLIC_PREFIX=/media/products/shared
```

Production switch for product originals:

```dotenv
PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER=r2
PRODUCT_MEDIA_ORIGINAL_S3_KEY_PREFIX=products/shared
```

## Migration Command

Report only:

```bash
python3 scripts/migrate_product_media_storage.py --provider r2 --limit 50
```

Scope to one product:

```bash
python3 scripts/migrate_product_media_storage.py --provider r2 --product-id 123 --limit 20
```

Execute a reviewed bounded batch:

```bash
python3 scripts/migrate_product_media_storage.py --provider r2 --limit 50 --execute
```

Production execution is manual-only. Start with dry-run output, verify target
URLs and skipped rows, then execute a small product-scoped batch before broader
runs.

The command updates `ProductImageVariant` rows only. It does not rewrite
`ProductImage.url`, `Product.main_image`, or `Product.images`, and it does not
delete local media files.

For legacy `Product.main_image` values that point at local files but do not have
a matching `ProductImage` row yet, use the main-image backfill helper:

```bash
python3 scripts/backfill_product_main_images_storage.py --provider r2 --limit 50
python3 scripts/backfill_product_main_images_storage.py --provider r2 --limit 50 --execute
```

This helper also preserves `Product.main_image`. When needed, it creates the
missing canonical `ProductImage(url=main_image)` row and stores an `original`
variant in R2, so public API mappers can expose the CDN URL through an exact
main-image match instead of guessing from gallery order.

For legacy `Product.images` array entries that point at local files but do not
have a matching `ProductImage` row yet, use the legacy-images backfill helper:

```bash
python3 scripts/backfill_product_legacy_images_storage.py --provider r2 --limit 50
python3 scripts/backfill_product_legacy_images_storage.py --provider r2 --limit 50 --execute
```

This helper preserves `Product.images`. When needed, it creates the missing
canonical `ProductImage(url=image_url)` row and stores an `original` variant in
R2, so public API mappers can expose CDN URLs while keeping local media as the
rollback source.

Manual and legacy rows that already point at `media/products` remain
local/manual fallback data until migrated or intentionally retained. New
runtime writes should go through `ImageService`,
`ProductOriginalMediaService`, `ProductImageVariantService`, or
`GeneralMediaStorage` so production can route them to R2/CDN.

## Rollback

1. Set `PRODUCT_MEDIA_STORAGE_PROVIDER=local` and redeploy/recreate the backend
   containers. Newly generated variants will return to local storage.
2. Existing local product image URLs continue to work because local `/media` is
   still mounted and product original fields were not rewritten.
3. Local original source files written before the R2 switch remain on disk and
   are not deleted automatically. New production originals should point at CDN
   URLs while `PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER=r2`.
4. If CDN variant URLs must be removed from responses, restore the pre-migration
   database backup or mark affected variants non-approved/non-ready and re-run
   variant processing with local provider.
5. Keep local media mounted until the owner explicitly approves final cutover and
   cleanup.

## Issue 428 Rollout Decision

Recommendation: approve a bounded manual smoke first, then switch
`PRODUCT_MEDIA_STORAGE_PROVIDER=r2` for normal new product media writes if the
smoke passes. A direct switch is technically available, but the first production
write should still be observed end-to-end because public catalog responses only
serve generated CDN variants after those rows are `ready` and
`manual_quality_status=approved`.

This is a write-provider decision only:

- Do not delete local media.
- Do not rewrite `ProductImage.url`, `Product.main_image`, or legacy
  `Product.images`.
- Keep `PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER=r2` after the full media switch.
- Existing importer main-image fields may remain local `/media/...` URLs until
  they are naturally rewritten or backfilled.
- R2 rows created during smoke or rollout live in `ProductImageVariant`.
- Set `MEDIA_STORAGE_PROVIDER=r2` only when order/bot attachments and media
  library uploads should start writing to R2.

### Production Env Diff

Use placeholders for secrets and confirm existing values on the server before
changing the provider. If the R2 variables are already present in production,
the effective owner-approved diff is only the provider line.

```diff
-PRODUCT_MEDIA_STORAGE_PROVIDER=local
+PRODUCT_MEDIA_STORAGE_PROVIDER=r2
PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER=r2
PRODUCT_MEDIA_LOCAL_ORIGINAL_DIR=media/products/shared
PRODUCT_MEDIA_LOCAL_ORIGINAL_PUBLIC_PREFIX=/media/products/shared
+PRODUCT_MEDIA_S3_BUCKET=<existing-r2-bucket>
+PRODUCT_MEDIA_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
+PRODUCT_MEDIA_S3_REGION=auto
+PRODUCT_MEDIA_S3_ACCESS_KEY_ID=<existing-r2-access-key-id>
+PRODUCT_MEDIA_S3_SECRET_ACCESS_KEY=<existing-r2-secret-access-key>
+PRODUCT_MEDIA_S3_PUBLIC_BASE_URL=https://cdn.mvn.by/media
+PRODUCT_MEDIA_S3_KEY_PREFIX=products/variants
+PRODUCT_MEDIA_ORIGINAL_S3_KEY_PREFIX=products/shared
+PRODUCT_MEDIA_S3_CACHE_CONTROL=public, max-age=31536000, immutable
+MEDIA_STORAGE_PROVIDER=r2
+MEDIA_S3_KEY_PREFIX=
```

Never commit or paste real access keys into an issue, PR, log, or chat.

### Preflight Without Leaking Values

Run from a trusted operator machine. The commands below print only presence,
shape, or public test URLs.

```bash
ssh <prod-host> 'cd /opt/air-api && docker compose -f docker-compose.prod.yml exec -T app python3 - <<'"'"'PY'"'"'
import os
from urllib.parse import urlparse

names = [
    "PRODUCT_MEDIA_STORAGE_PROVIDER",
    "PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER",
    "PRODUCT_MEDIA_S3_BUCKET",
    "PRODUCT_MEDIA_S3_ENDPOINT_URL",
    "PRODUCT_MEDIA_S3_REGION",
    "PRODUCT_MEDIA_S3_ACCESS_KEY_ID",
    "PRODUCT_MEDIA_S3_SECRET_ACCESS_KEY",
    "PRODUCT_MEDIA_S3_PUBLIC_BASE_URL",
    "PRODUCT_MEDIA_S3_KEY_PREFIX",
    "PRODUCT_MEDIA_S3_CACHE_CONTROL",
]

for name in names:
    value = os.getenv(name, "")
    if name.endswith("_ACCESS_KEY_ID") or name.endswith("_SECRET_ACCESS_KEY"):
        print(f"{name}: {'set' if value else 'MISSING'}")
    elif name.endswith("_ENDPOINT_URL") or name.endswith("_PUBLIC_BASE_URL"):
        parsed = urlparse(value)
        shape = f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if value else ""
        print(f"{name}: {'set' if value else 'MISSING'} ({shape or 'n/a'})")
    else:
        print(f"{name}: {'set' if value else 'MISSING'}")
PY'
```

Confirm the R2 dry-run storage factory can build CDN targets without requiring
write credentials:

```bash
ssh <prod-host> 'cd /opt/air-api && docker compose -f docker-compose.prod.yml exec -T app python3 scripts/migrate_product_media_storage.py --provider r2 --limit 5'
```

Confirm all runtime media classes target object storage:

```bash
ssh <prod-host> 'cd /opt/air-api && docker compose -f docker-compose.prod.yml exec -T app python3 scripts/check_media_storage_config.py --require-object-storage --expected-public-base-url https://cdn.mvn.by'
```

Expected preflight result:

- `PRODUCT_MEDIA_STORAGE_PROVIDER` may still be `local`.
- `PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER` is `r2` for the full media switch.
- R2 bucket, endpoint, region, access key id, secret access key, public base
  URL, key prefix, and cache control are present.
- Dry-run output builds `https://cdn.mvn.by/media/products/variants/...` target
  URLs and does not attempt writes.

### Bounded Manual Smoke

Use one throwaway product and one non-installation image. Prefer an unpublished
or clearly marked test product so public response checks do not affect real
catalog merchandising.

1. Take a DB backup or confirm the latest backup is fresh enough for rollback.
2. Change `PRODUCT_MEDIA_STORAGE_PROVIDER`,
   `PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER`, and `MEDIA_STORAGE_PROVIDER` to
   `r2` in production env and recreate the backend containers.
3. Run public smoke checks:

   ```bash
   curl -fsS https://api.mvn.by/api/health
   curl -fsS 'https://api.mvn.by/api/v1/products?limit=5' >/tmp/products.json
   curl -fsS https://api.mvn.by/api/v1/filters/config >/tmp/filters.json
   ```

4. Attach the test image through one manager bytes-ingest path:
   - local upload: `POST /api/manager/upload-local-images?product_id=<id>`, or
   - search/download attach:
     `POST /api/manager/gallery/link-search-result?product_id=<id>&url=<image-url>`.

   Both paths converge in `ManagerMediaService.save_image_from_bytes(...)`.

5. Verify the attached `ProductImage.url`, `Product.main_image` if set, and
   importer/cache URLs use `https://cdn.mvn.by/...` for newly written media.
6. Verify the `original` variant row for that image is ready on R2:

   ```sql
   select variant_type, storage_provider, processing_status, manual_quality_status, url
   from productimagevariant
   where product_image_id = <image_id>
   order by variant_type;
   ```

   Expected for `original`: `storage_provider='r2'`,
   `processing_status='ready'`, and
   `url like 'https://cdn.mvn.by/media/products/variants/original/%'`.

7. Generate `card` and `full` variants for the same image:

   ```bash
   curl -fsS -X POST '<manager-authenticated-api>/api/manager/gallery/<image_id>/variants/reprocess?variant_type=card&provider=noop'
   curl -fsS -X POST '<manager-authenticated-api>/api/manager/gallery/<image_id>/variants/reprocess?variant_type=full&provider=noop'
   ```

   Expected rows: `storage_provider='r2'`, `processing_status='ready'`, CDN
   URLs under `/products/variants/card/` and `/products/variants/full/`.

8. Because public product responses intentionally require approved generated
   variants, approve only the smoke rows after visual review:

   ```sql
   update productimagevariant
   set manual_quality_status = 'approved'
   where product_image_id = <image_id>
     and variant_type in ('card', 'full')
     and storage_provider = 'r2'
     and processing_status = 'ready';
   ```

9. Fetch the product and catalog/list response that includes it:

   ```bash
   curl -fsS 'https://api.mvn.by/api/v1/products/<slug-or-id>' >/tmp/product.json
   curl -fsS 'https://api.mvn.by/api/v1/products?limit=100' >/tmp/catalog.json
   ```

   Expected product response:
   - newly written original URLs use `https://cdn.mvn.by/...`;
   - `card_image`, `full_image`, `gallery_images[].card_variant_url`, and
     `gallery_images[].full_variant_url` use `https://cdn.mvn.by/...` for the
     approved generated variants.
   - pre-existing legacy rows may still show local `/media/...` until migrated.
   - If approval is removed or a variant is not ready, `card_image` and
     `full_image` fall back to the local original URL.

10. Confirm importer behavior by running or observing a small importer path only
    if the owner wants this in the same window. Expected:
    `ImportMediaService` writes CDN URLs into importer product fields/cache when
    `PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER=r2`.

### Full Switch

After the bounded smoke passes and the owner approves the full switch:

1. Keep `PRODUCT_MEDIA_STORAGE_PROVIDER=r2`.
2. Set `MEDIA_STORAGE_PROVIDER=r2` to write articles, media library uploads,
   order attachments, and bot attachments to R2.
3. Keep `PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER=r2` after confirming product
   variant regeneration can read original images from
   `PRODUCT_MEDIA_S3_PUBLIC_BASE_URL`.
4. Monitor backend logs for `S3/R2 media storage` errors and Pillow processing
   failures during normal manager uploads/search attaches and variant
   generation.
5. Keep the scheduled `check-media-cdn.yml` workflow green. It samples public
   catalog image URLs and DB-backed object-storage rows from the API primary,
   including product variants, media library assets, and order/bot attachments.
6. Spot-check new manager media rows daily during the first rollout window:

   ```sql
   select variant_type, storage_provider, processing_status, count(*)
   from productimagevariant
   where updated_at >= now() - interval '1 day'
   group by variant_type, storage_provider, processing_status
   order by variant_type, storage_provider, processing_status;
   ```

6. Keep local `/media` mounted and backed up.

### Rollback From Smoke Or Switch

1. Set `PRODUCT_MEDIA_STORAGE_PROVIDER=local` and recreate the backend
   containers.
2. Confirm `/api/health`, `/api/v1/products?limit=5`, and
   `/api/v1/filters/config` still pass.
3. New product media writes and generated variants return to local storage.
4. Local product originals that existed before the switch remain available
   because they were never deleted.
5. R2 `ProductImageVariant` rows created during the test remain in the database
   and may still be returned if they are `ready` and approved. For the smoke
   product, either leave them as historical variant rows, mark them
   `manual_quality_status='rejected'`, or delete/reprocess only the smoke
   variants after owner approval. Do not bulk-delete R2 objects or rows during
   emergency rollback.
6. If no CDN URLs should remain visible, restore the pre-smoke DB backup or
   explicitly mark affected generated variants non-approved and reprocess them
   with the local provider.

### Residual Risks And Follow-Ups

- Existing importer main images and import-media cache rows may remain local
  original URLs until they are backfilled or naturally rewritten.
- Manual and legacy rows under `media/products` remain local/manual unless a
  future issue migrates them.
- Cleanup and dedupe scripts need an owner-approved policy before deleting local
  files or R2 objects.
- Generated CDN variants are public only after manual quality approval; a
  manager approval endpoint/UI is a useful future workflow but not required for
  the provider switch.
- A later full legacy-media cutover would need a separate plan for rewriting old
  product original fields, backup/restore semantics, and local-media retention.

### Owner Decisions

- Approve or skip the bounded one-product R2 smoke.
- Approve the full provider switch after smoke passes.
- Decide who monitors the first rollout window and which logs/SQL summaries are
  considered sufficient.
- Decide whether to open follow-up issues for importer original variants,
  variant approval UX, cleanup/dedupe policy, and a possible full original-media
  cutover.
