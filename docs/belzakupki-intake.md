# Belzakupki → Kitlane incoming leads

Belzakupki is an independent service. Kitlane consumes its tenant/profile-scoped
HTTP API, without database access or embedding its scraping/OCR dependencies.

## Runtime configuration

The active-primary scheduler imports at most one page per interval. Standby
scheduler fencing remains unchanged. Configure protected `.env` on **both** API
nodes so the selected primary can own the same import after failover:

```dotenv
BELZAKUPKI_IMPORT_ENABLED=true
BELZAKUPKI_API_BASE_URL=https://maxikor.fun
BELZAKUPKI_INTEGRATION_KEY=<protected-service-key>
BELZAKUPKI_IMPORT_TENANT_SLUG=mvn
BELZAKUPKI_IMPORT_STOREFRONT_SLUG=main
BELZAKUPKI_IMPORT_INTERVAL_MINUTES=5
BELZAKUPKI_IMPORT_PAGE_SIZE=100
BELZAKUPKI_IMPORT_INCLUDE_RULES_ONLY=false
BELZAKUPKI_IMPORT_TIMEOUT_SECONDS=10
```

The API key belongs to the configured source tenant. Belzakupki's optional
`INTEGRATION_PROFILE_IDS` allowlist restricts the first rollout to the existing
HVAC profile. Do not point the importer at another customer's source key or
change destination slugs to implicitly merge their data.

## Data and recovery contract

- New eligible, AI-confirmed tenders create `Order(status=new_lead)` and therefore
  appear in the existing Manager inbox. No Customer is invented. The customer
  name can be shown directly from the source metadata until staff qualifies it.
- The existing unique order fingerprint includes a provider namespace, source
  and tender external ID, under destination tenant/storefront scope. Multiple
  matching profiles create one order; their metadata is stored by match ID.
- Full scans deliberately replay rows. Unchanged fingerprints are skipped;
  changes, including rejected/expired states, update only provider-owned metadata.
  Staff comments, titles and workflow status are never overwritten or reopened.
- `rules_only` means the AI analysis was bypassed, not that it confirmed relevance.
  It is excluded by default. Enabling it is an explicit operational choice.
- A new `belzakupki_import_checkpoint` row stores the opaque cursor. Page writes
  and checkpoint advancement commit together. The checkpoint is locked before
  writes; a stale concurrent page cannot advance it. The terminal page resets
  to null so the next interval begins a fresh scan and sees older record updates.
- Failed requests/pages leave the cursor unchanged and retry at the next interval.
  Logs use `BELZAKUPKI_IMPORT` / `BELZAKUPKI_IMPORT_FAILED` without the API key.
  These are current-state reconciliations, not a deletion/event archive.

Apply migration `e64f5a6b7c8d` through the normal reviewed deployment path before
starting this importer. Disabling `BELZAKUPKI_IMPORT_ENABLED` and redeploying
stops new intake without deleting orders/checkpoints. Rollback of application
code does not require dropping the additive checkpoint table.

## Shared-host deployment

Follow [the deployment guard](deployment.md) to enable the root-owned marker on
the Belarus host. The guard pauses only Belzakupki scheduler and worker during
Kitlane migration/deploy, preserves the existing stopped/running state, and
restores it on success or failure. It does not change Caddy, PostgreSQL, Redis,
or Belzakupki API routing. A busy worker must finish gracefully within the
configured wait or the deployment aborts; the guard never forces a job kill.

## Verification

Before activation, verify source API 401 without a key, a scoped successful page
with the protected key, and the actual destination tenant/storefront. Check the
source `/api/health` and `/api/ready`. After deployment inspect scheduled import
logs/checkpoint and confirm created orders through the existing inbox API.
A valid page with no eligible current tenders must create **zero** test or fake
leads. Idempotency, rollback, scope isolation and concurrency are covered in
`test_belzakupki_import_service.py` and `test_belzakupki_import_concurrency.py`.
