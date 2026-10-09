# Belzakupki → Kitlane incoming leads

Belzakupki is an independent service. Kitlane consumes its tenant/profile-scoped
HTTP API, without database access or embedding its scraping/OCR dependencies.

## Direct push intake (#849, first release slice)

`POST /api/integrations/tenders/leads` accepts **one native opportunity** from
the same source contract as the existing pull feed. It uses a separate inbound
Bearer key, not a Manager token or the outbound `BELZAKUPKI_INTEGRATION_KEY`.
The endpoint is disabled by default; this release does not configure or activate
the external publisher. Existing scheduled import settings remain authoritative.

```dotenv
BELZAKUPKI_LEAD_PUSH_ENABLED=false
BELZAKUPKI_LEAD_PUSH_API_KEY=
```

Activation requires a protected dedicated key on both API nodes and the existing
`BELZAKUPKI_IMPORT_TENANT_SLUG` / `BELZAKUPKI_IMPORT_STOREFRONT_SLUG` destination.
The destination must be the active system tenant and its active default
storefront, outside demo read-only mode. The request cannot choose a destination.
App-role/readiness fencing and the PostgreSQL writable-primary check also apply.
Disabling the flag and redeploying stops push intake without deleting orders or
changing pull configuration. No migration is added by this slice.

Example source shape (IDs must come from the producer, never be synthesized):

```json
{
  "id": 123,
  "profile": {"id": 7, "name": "HVAC"},
  "score": 0.91,
  "relevance_status": "confirmed",
  "eligible": true,
  "reason": "Air conditioning equipment",
  "updated_at": "2026-10-09T10:00:00+00:00",
  "tender": {
    "source": "goszakupki",
    "external_id": "source-tender-id",
    "title": "Air conditioning equipment procurement",
    "customer_name": "Source buyer",
    "url": "https://example.org/tenders/source-tender-id",
    "deadline_at": "2026-11-01T10:00:00+00:00"
  }
}
```

The typed schema rejects unknown fields, non-positive or string IDs,
non-boolean eligibility, naive timestamps, non-finite numbers and unsafe source
URLs. Source URLs must be HTTP(S), without credentials or whitespace. Serialized
validated source evidence is limited to 64 KiB; this is a model validation bound,
not a raw HTTP transport-size limit. Optional fields and their limits are in
[OpenAPI](../openapi.json).

A successful `200` returns `order_id` (nullable), `outcome` (`created`, `updated`,
`unchanged` or `skipped`), `source` and `external_id`. Creation follows the same
eligibility, deadline and `rules_only` rules as pull. Nonactionable new records
are skipped; existing records receive source updates without reopening workflow.
Source/external ID under the configured tenant/storefront identifies one order,
including concurrent pull/push and multiple profile matches. Manager fields and
reviewed enrichment remain authoritative. Older match updates are ignored;
an older different profile can be recorded without replacing newer tender data.

Both transports take the same checkpoint lock before upsert. Push may initialize
the shared checkpoint but never advances an existing pull cursor or its timestamp.
It performs no source HTTP request, customer creation, qualification, pricing,
document generation or messaging. Existing optional shadow observation remains
best effort after commit. Logs contain outcome/failure codes, not source text or
credentials. Default request-validation errors may echo offending input values;
the producer must put credentials only in the Authorization header.

Missing/wrong credentials return `401` (`invalid_integration_credentials`) when
the intake is configured. Disabled/incomplete configuration or an unwritable
database returns `503` (`tender_intake_unavailable`); unavailable destination
returns `403` (`tender_intake_scope_denied`); invalid source payload returns `422`.
The outer HA fence may instead return `503` with `api_write_fenced` before routing.
Retry a transient failure with the same native opportunity; do not invent a new
match ID. Wiring the producer and integration settings/status are subsequent
slices of #849; this endpoint alone does not complete the full integration.

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

## Manager review and source documents

The inbox action **Проработать** and the order action **Дозаполнить из источника**
request fresh details for the order's saved provider source and external ID. The
source API must be deployed before these actions are enabled in Kitlane. Access
uses the same integration key and tenant/profile scope as the intake feed. A
missing or unavailable source returns an error without changing the order.

The preview is read-only. It combines collector fields and bounded extracted
document text, proposes customer type and contacts, and separates explicitly
identified service sites. The original document opens through an authenticated
Manager route; selected originals are copied to private order attachments only
after manager confirmation. **Обработать ИИ** is a separate, on-demand draft
step for selected documents. Its suggested work and equipment are reviewable
and can be edited before applying. The order scenario is suggested from the
procurement title or AI work summary; ambiguous text requires a manual choice.
The manager can change the suggestion before saving. It does not set a proposal
price from the procurement's estimated value.

Customer drafts carry source-backed requisites. The collector reads the buyer
UNP and address
from explicitly labelled rows, excluding platform operator details. The preview
checks the UNP against the existing public registry lookup; an outage leaves the
source draft reviewable with a warning. Documented branches remain separate
choices, with their own UNP and bank account. Existing customer fields are filled
only when missing and the reviewed party identity matches; staff values remain
authoritative. Contacts retain their purpose and supporting document text.
A matching customer already linked to the order takes precedence over other
UNP matches. Other matching cards produce a warning; historical orders are not
relinked or customers merged by source review.

The submission marker distinguishes an explicitly stated email destination from
submission through an electronic platform. A generic contact email, a deadline,
or the procurement amount does not establish a submission channel. Missing or
conflicting instructions show that the method needs clarification. Confirmation
stores the marker and contact evidence in order source metadata.

UNP input and OCR use the same numeric-field rules: known lookalikes such as
`З` → `3` are normalized, while unknown characters and identifiers longer than
nine digits are rejected. These replacements never apply to email or names.
Bank identifiers use their existing separate validation. AI input includes all
selected extracted texts up to a shared 180,000-character limit; exceeding the
limit fails explicitly rather than silently dropping later documents. A source
document with truncated text must be re-extracted or reviewed manually.

Applying reviewed data links an existing tenant customer or creates a customer
with the chosen party type, then saves source work details and distinct object
addresses. A new lead advances to negotiation only after a customer is linked
and a scenario is selected. The reviewed scenario updates the order workflow
and service type together. Previously entered order fields remain authoritative
unless the manager explicitly changes them; reopening review starts
from the saved reviewed enrichment. Repeated application reuses already attached
source documents and object addresses. This path has no automatic backfill:
existing orders such as #455 are enriched when a manager opens and confirms the
source review.

For **Продажа и монтаж**, applying reviewed objects also appends equipment to
the selected draft proposal when the full model has exactly one match in the
manager's scoped catalog, a current selling price and enough available stock
for the summed quantity across objects. Matching ignores case, whitespace and
equivalent dash characters; it never uses partial model names. The explicit
`(WF)` marker on an indoor/outdoor pair is accepted only when both canonical
component models match and the catalog confirms built-in Wi-Fi. The price and
cost come from the same storefront and supply projection as manual selection;
unknown cost produces a warning. Adding a line does not reserve stock.

Ambiguous, incomplete, unavailable or unpriced items remain for manual
selection, with a saved report in source review. Existing proposal lines keep
their quantity and price. A source provenance ledger survives importer refresh
and prevents repeated review from duplicating items or recreating equipment a
manager removed. Installation is added separately through
**Добавить стандартный монтаж** or the editable installation estimate.

Changing the scenario to **Продажа и монтаж** reuses confirmed saved equipment
even when a later source apply omits `objects`. Explicit `objects: []` clears the
reviewed list; `objects: null` suppresses equipment transfer for that apply.
Models with no known object address remain reviewable without inventing an
address or an installation allocation.

The collapsed source card reads saved reviewed evidence and already attached
originals locally. Expanded details show model quantities, original filenames,
literal installation facts and the complete reviewed request text on demand.
Files open through authenticated Manager attachment access. The card requires
an active attachment link to the scoped order and the same source identity.
Route lengths such as 5/8/10 metres are evidence to verify by room; they do not
silently become priced installation lines or a guessed equipment allocation.

**Добавить из заявки** loads a read-only preview through
`GET /api/manager/orders/{order_id}/source-equipment?proposal_id=...`.
`POST` to the same path appends only selected eligible products after verifying
the preview fingerprint, current stock, price and draft status under the order
lock. Manual lines keep their price and quantity. Removed equipment needs the
separate unchecked restoration choice; equipment previously added to another
proposal is labelled as a repeat addition. Each explicit command carries an
idempotency ID: retrying it cannot recreate a line removed after that command.
The editor saves pending changes before this action and awaits a fresh order
projection before allowing further edits. No stock reservation occurs.

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

## Procurement stages and price enquiry history

Manager can explicitly associate an announced procurement with an earlier
price enquiry, including an archived enquiry or one already qualified into an
order. The two Orders retain their source IDs, proposals, documents, statuses
and archive history. The inbox and order workspace show navigation in both
directions. A manager can remove the association; its creation and removal are
audited on both records. Buyer names and similar titles never establish a link
automatically. An unmarked source can be explicitly marked as a price enquiry
when selecting it.

Business stages are price enquiry, price sent, announced/preparing, submitted
and completed. The current stage's deadline is optional and displayed in Minsk
time. Manual context is stored separately from importer metadata and used by
deadline sorting before pagination. The original publication and source dates
remain available. A linked price enquiry, an already submitted bid or a
completed procurement is excluded from automatic missed-deadline archiving.
Other incoming cards retain the existing 24-hour grace and restore policy.

`GET/PATCH /api/manager/orders/{order_id}/tender-workflow` reads or updates the
scoped context. The `/price-enquiries` child route lists bounded candidates;
`PUT/DELETE /price-enquiry` creates or removes an explicit association. Commands
lock both Orders in ascending ID order and preserve tenant/storefront boundaries.
Repeated association with the same target or repeated removal is safe; changing
the target requires removing the existing association first.

### Release scope and rollback

Acceptance covers explicit linking/unlinking, archived/qualified sources,
independent deadlines, importer preservation, scope isolation and the existing
document/email workflows. Platform submission, automatic matching, reminders
and AI qualification are outside this release.

The additive migrations `t1089chain01` and `t1089scan02` create independent
context/link and registration-certificate tables without backfilling Orders or
replacing business documents. Deploy through the normal migration/image gates.
Application rollback can leave the new tables in place. Do not downgrade/drop
them in production after use: that would discard manually saved history and
certificate metadata.

## Verification

Before activation, verify source API 401 without a key, a scoped successful page
with the protected key, and the actual destination tenant/storefront. Check the
source `/api/health` and `/api/ready`. After deployment inspect scheduled import
logs/checkpoint and confirm created orders through the existing inbox API.
A valid page with no eligible current tenders must create **zero** test or fake
leads. Idempotency, rollback, scope isolation and concurrency are covered in
`test_belzakupki_import_service.py` and `test_belzakupki_import_concurrency.py`.
Direct push contract, no-write gates, shared concurrency and checkpoint
preservation are covered in `test_belzakupki_intake_schema.py` and
`test_belzakupki_lead_push.py`. Release acceptance for this disabled slice reads
configuration/schema and runs public smoke checks; it inserts no production
test leads.
