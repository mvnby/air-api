# Private service attachments

Photos of customer premises, equipment nameplates, work reports, documents and
voice messages are stored separately from the public media library.

## Storage

- Local development uses `SERVICE_ATTACHMENT_STORAGE_PROVIDER=local` and writes
  to `private_media/service-attachments`.
- Production must use `r2` (or `s3_compatible`) with a dedicated private bucket.
- Do not configure a public base URL for this bucket. Manager access is granted
  with short-lived signed links only.
- The original is immutable. Image previews are generated with corrected EXIF
  orientation and without EXIF/GPS metadata.

Required production variables:

```env
SERVICE_ATTACHMENT_STORAGE_PROVIDER=r2
SERVICE_ATTACHMENT_S3_BUCKET=<private-bucket>
SERVICE_ATTACHMENT_S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com
SERVICE_ATTACHMENT_S3_REGION=auto
SERVICE_ATTACHMENT_S3_ACCESS_KEY_ID=<write-key>
SERVICE_ATTACHMENT_S3_SECRET_ACCESS_KEY=<write-secret>
SERVICE_ATTACHMENT_S3_KEY_PREFIX=service-attachments
SERVICE_ATTACHMENT_ACCESS_TTL_SECONDS=300
```

The credentials need read/write access only to this bucket. Public access and a
custom public domain must remain disabled.

## Legacy migration

Review the migration without changing data:

```bash
python3 scripts/migrate_service_attachments.py
```

Limit the report to one order before the first production run:

```bash
python3 scripts/migrate_service_attachments.py --order-id 123
```

After reviewing the report, execute the same bounded run:

```bash
python3 scripts/migrate_service_attachments.py --order-id 123 --execute
```

The script preserves all legacy JSON fields and legacy warranty columns. It is
safe to run repeatedly: existing attachment and equipment links are skipped.
Telegram files that can no longer be downloaded are reported as unavailable
and remain visible in Manager as legacy records awaiting manual recovery.
