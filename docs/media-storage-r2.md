# Product Media Storage: R2/S3 Migration

This project keeps local product image URLs working while moving product media
variant copies to public S3-compatible object storage such as Cloudflare R2.

## URL Strategy

- `ProductImage.url`, `Product.main_image`, and legacy `Product.images` remain
  local `/media/...` URLs during the transition.
- Manager uploads and search/download attaches write the local source original
  to `/media/products/shared/{sha256}.webp`, then write/update
  `ProductImageVariant(variant_type=original)` through
  `PRODUCT_MEDIA_STORAGE_PROVIDER`.
- Import media downloads also write the local source original through the
  source storage adapter. Product importer main-image fields remain local URLs;
  importer main images are not converted into remote `ProductImageVariant`
  records during this transition.
- Generated rows in `ProductImageVariant`, plus new manager-uploaded
  `original` variant rows, can use `storage_provider=r2` (or
  `s3`/`s3_compatible`) and public CDN URLs.
- The public API already falls back to the original local URL when an approved
  ready variant is absent, so local media remains the rollback path.
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
```

Cloudflare R2 example:

```dotenv
PRODUCT_MEDIA_STORAGE_PROVIDER=r2
PRODUCT_MEDIA_S3_BUCKET=mvn-product-media
PRODUCT_MEDIA_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
PRODUCT_MEDIA_S3_REGION=auto
PRODUCT_MEDIA_S3_ACCESS_KEY_ID=<secret>
PRODUCT_MEDIA_S3_SECRET_ACCESS_KEY=<secret>
PRODUCT_MEDIA_S3_PUBLIC_BASE_URL=https://cdn.mvn.by/media
PRODUCT_MEDIA_S3_KEY_PREFIX=products/variants
PRODUCT_MEDIA_S3_CACHE_CONTROL=public, max-age=31536000, immutable
```

Dry-run migration requires bucket, endpoint, public base URL, and key prefix so
it can print target keys. Secret access keys are only required for writes.

The original source provider is local-only for this transition. The optional
local path overrides are:

```dotenv
PRODUCT_MEDIA_LOCAL_ORIGINAL_DIR=media/products/shared
PRODUCT_MEDIA_LOCAL_ORIGINAL_PUBLIC_PREFIX=/media/products/shared
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

Manual and legacy writers that write under `media/products` remain local/manual
tools unless a future issue explicitly migrates them: examples include
`services/image_service.py` via older product/article/order paths,
`scripts/dedupe_product_media.py`, `scripts/refetch_images.py`,
`scripts/search_images_ddg.py`, and `scripts/import_mdv.py`.

## Rollback

1. Set `PRODUCT_MEDIA_STORAGE_PROVIDER=local` and redeploy/recreate the backend
   containers. Newly generated variants will return to local storage.
2. Existing local product image URLs continue to work because local `/media` is
   still mounted and product original fields were not rewritten.
3. New local original source files written during an R2 provider test remain on
   disk and are not deleted automatically. Manager-created `original` variant
   rows may point at CDN URLs, but product-facing original fields still point at
   local `/media/products/shared/...` URLs.
4. If CDN variant URLs must be removed from responses, restore the pre-migration
   database backup or mark affected variants non-approved/non-ready and re-run
   variant processing with local provider.
5. Keep local media mounted until the owner explicitly approves final cutover and
   cleanup.

## Deploy Checklist

- Create an R2 bucket and a public custom domain or public base URL.
- Set production env/secrets listed above in `/opt/air-api/.env`; do not commit
  secret values.
- Keep `PRODUCT_MEDIA_STORAGE_PROVIDER=local` until dry-run output is reviewed.
- Deploy backend image and run smoke checks: `/health`,
  `/api/v1/products?limit=5`, `/api/v1/filters/config`.
- Run a dry-run migration inside the app container.
- Execute only a small, reviewed batch after owner approval.
- Verify product API responses and public CDN URLs before increasing batch size.
