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

## Order request evidence

`GET /api/manager/orders/{order_id}/request-context` projects saved source text
and unique files into Manager's “Заявка и файлы” panel beside proposal preparation.
The order must be accessible in the current tenant/storefront. System email orders
also require the same live staff membership as the existing saved-mail reader.
It reads local metadata only: no IMAP request, AI, file download, copy, grant or
business-data mutation. Repeated GET is safe. Missing/inaccessible orders return
404; missing live mailbox permission returns 403.

Private order links and saved incoming-mail attachment metadata are merged by
SHA-256; an available saved original takes precedence over an unavailable copy.
Unknown hashes are never guessed from filenames. Unavailable legacy and unsaved
mail files remain visible and counted. The count describes the returned unique
records; import omissions are separately disclosed as warnings. Originals retain
the existing authenticated service-attachment/mail download routes and byte
integrity checks. No permanent public URL is exposed. Generated outgoing offers
and invoices remain in Documents.

The editable order comment is labelled “Рабочее описание заказа”; it is never
presented as verbatim source wording. Email source text comes from saved incoming
messages or explicitly saved source metadata, while tender enrichment is labelled
as a reviewed tender request. Missing/truncated source text is explicit. Opening
the panel does not save or replace proposal/comment drafts.
