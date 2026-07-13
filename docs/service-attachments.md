# Private service attachments

Photos of customer premises, equipment nameplates, work reports, documents and
voice messages are stored separately from the public media library.

## Storage

- Local development uses `SERVICE_ATTACHMENT_STORAGE_PROVIDER=local` and writes
  to `private_media/service-attachments`.
- Production must use `r2` (or `s3_compatible`) with a dedicated private bucket.
- Production configuration is fail-closed: the API refuses to start with local
  storage or incomplete private bucket credentials.
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

Before executing the legacy migration, the script writes, reads and removes a
small probe object. Migration stops before changing the database when this
preflight fails.

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

The dry run downloads and validates every available source without writing the
database. The script preserves all legacy JSON fields and legacy warranty
columns and is safe to run repeatedly. Existing occurrences and equipment links
are skipped, while identical file bytes reuse one private object. Telegram files
that can no longer be downloaded are reported as unavailable and remain visible
in Manager as legacy records awaiting manual recovery.

Legacy HTTP sources are restricted to HTTPS hosts already configured as MVN
public media/site origins; every redirect is validated again. When a legacy URL
is unavailable and a Telegram `file_id` is present, the script retries through
Telegram. Known SHA-256 and size metadata are checked before import, and execute
mode reads every saved private object back before committing.

By default any missing file or conflicting equipment link rolls the execute run
back. `--allow-partial` is an explicit recovery option only after a reviewed dry
run. Public legacy copies are not removed by this migration; cleanup remains a
separate, signed-off operation after the private-copy report is complete.
