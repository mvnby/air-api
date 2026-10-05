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

## Verification

Before activation, verify source API 401 without a key, a scoped successful page
with the protected key, and the actual destination tenant/storefront. Check the
source `/api/health` and `/api/ready`. After deployment inspect scheduled import
logs/checkpoint and confirm created orders through the existing inbox API.
A valid page with no eligible current tenders must create **zero** test or fake
leads. Idempotency, rollback, scope isolation and concurrency are covered in
`test_belzakupki_import_service.py` and `test_belzakupki_import_concurrency.py`.
