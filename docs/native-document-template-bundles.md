# Native document template bundles

Template bundles solve first-run onboarding without putting tenant-owned DOCX
files, logos, seals, or signatures into Git. Git contains only a reviewed
manifest with metadata and SHA-256 checksums. The DOCX files are supplied from
a private directory and written directly to the tenant's private template
storage.

## Safe workflow

1. Put every DOCX named by the manifest into a private source directory.
2. Run the read-only plan. It validates every checksum and DOCX placeholder
   contract before reading or changing database state:

   ```bash
   python3 scripts/manage_native_document_template_bundle.py plan \
     --manifest config/native_document_template_bundles/mvn-2026-v1.json \
     --source-dir /private/path/to/templates \
     --tenant-id 1 \
     --legal-entity-id 1
   ```

3. Review the plan. Apply requires the exact bundle id:

   ```bash
   python3 scripts/manage_native_document_template_bundle.py apply \
     --manifest config/native_document_template_bundles/mvn-2026-v1.json \
     --source-dir /private/path/to/templates \
     --tenant-id 1 \
     --legal-entity-id 1 \
     --confirm-bundle-id mvn-2026-v1
   ```

The command is idempotent: it reuses a canonical name or declared alias,
updates scenario metadata, and uploads a version only when the active SHA-256
differs. It never deletes a template or historical version.

Only one apply for the same tenant and seller can run at a time on
PostgreSQL; a second operator gets a clear refusal instead of duplicate cards.
Database rows and private object storage cannot share one transaction, so a
storage or database failure may stop after some templates were activated. The
error names the failed key. Fix the cause and repeat the exact same apply: the
idempotent plan skips every already matching version and resumes the remainder.
Always finish by running `plan` again; every action must be `keep`.

## Partner onboarding

Partners do not need a Google Cloud project for native generation. Create their
seller legal entity, upload or import their own DOCX versions, and configure
official numbering. A Google account is required only when they explicitly
choose the separate legacy Google mode.

Electronic invoices and electronic waybills are outside this bundle. The
current TN-2/TTN-1 path produces printable files only; ESF/EDI integration stays
deferred until a tenant actually needs it.
