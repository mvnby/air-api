# Development workflow

Read the section relevant to the change. Commands below run from the repository
root unless noted. For production data, first read [production data operations](production-data-operations.md); local backfill examples do not authorize production writes.

## Commands

Run from repo root unless noted.

### Environment and App

- Start stack (API + DB): `docker compose up -d`
- Stop stack: `docker compose down`
- API logs: `docker compose logs -f app`
- Open API locally: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Dev server is on port 8000.**

### Backend Tests

- Start with the relevant existing test file(s), using the project environment:
  `scripts/test_local.sh --host tests/unit/test_public_warranty_projection.py -q`
  is an example; replace the path with tests for the changed behavior.
- Use `scripts/test_local.sh --docker <pytest args>` for an already running local
  app container, or `pytest <paths> -q` in the configured local venv.
- Broaden to `pytest tests/unit -q`, `pytest tests/integration -q` or `pytest`
  when shared dependencies, failures or unresolved risk justify it.
- Prove physical PostgreSQL isolation for four pytest workers:
  `EXPECT_XDIST_DATABASE_ISOLATION=1 pytest -q -n 4 --dist load tests/integration/test_postgres_worker_database_isolation.py`

PostgreSQL test policy:

- Every pytest process/xdist worker derives and owns a separate physical
  database from `TEST_DATABASE_URL`.
- Do not point `PYTEST_BASE_DATABASE_URL` at a production database. The test
  bootstrap rejects base database names without a `test` marker.
- CI runs both broad suites with four xdist workers after the four-worker
  database-isolation proof passes. Each worker owns a separate physical test DB.
  A speedup is not established until comparable post-change CI timings are available.

### Manager Frontend (Vue)

Run from `manager_frontend/`:

- Install locked deps when missing or the lockfile changed: `npm ci`
- Dev server: `npm run dev`
- Build: `npm run build`
- Preview build: `npm run preview`
- Regenerate API client from backend OpenAPI: `npm run gen:api`
  - Note: this project uses `--useUnionTypes` in codegen to avoid TS enum re-export issues.
- Run relevant component specs directly, for example:
  `npx vitest run --environment jsdom tests/customer-create.spec.ts`.
- Existing broader checks: `npm run test:components`, `npm run test:ui-logic`.

## CI routes

Every pull request and push to `main` or `master` runs the CI workflow. The
`changes` job always classifies the complete diff and checks every changed
Markdown file's local links, heading anchors, reference links and fenced code.
The required `test` gate always runs: it verifies that every selected lane
passed, or that every application lane was skipped on the documentation route.

The documentation-only route is limited to added or modified regular,
non-executable Markdown files under `docs/`, plus `README.md`, `AGENTS.md`,
`.github/copilot-instructions.md` and `.github/pull_request_template.md`. Any
other path, mixed change, empty or unknown diff, deletion, rename, file-type or
mode change, or classification error selects full CI. Full CI builds and tests
Manager, checks migrations and API-client freshness, and runs unit and
integration suites with four workers. Pull requests compare against their merge
base; pushes classify the exact pushed revision. A documentation-only push also
requires successful push CI for the exact preceding commit on that branch.
If that result is missing, still running or cannot be confirmed, the latest
commit runs full CI: a docs merge must not cancel and bypass pending code checks.

## Verification by change

Choose checks for the behavior and boundaries touched; this is not a requirement
to run every row. The required [CI](../.github/workflows/ci.yml) gate applies
before merge. Documentation-only changes use the checked Markdown route above;
other changes run all application lanes. Do not rerun successful local checks
unless the relevant code/environment changed or a failure/unresolved concern warrants it.

| Change | Local evidence |
| --- | --- |
| Markdown/instructions only | Review local link targets/anchors, fenced code blocks and preserved rules; run `git diff --check`. No local application build or DB suite is needed. |
| Backend behavior | Relevant unit/integration tests; cover changed contracts and failure cases. Use a separate physical PostgreSQL DB per process. |
| Manager UI | Relevant component/UI-logic checks, `npm run build` and inspection of the affected user flow; use browser evidence for visible behavior. |
| API route, operation ID or schema | Relevant backend checks, regenerate OpenAPI and client as below, build Manager and commit changed generated artifacts. |
| Migration, production or HA | Relevant contract checks plus the rollout/rollback and runtime checks in the matching runbook; data mutations also require production-data gates. |

For documentation, verify every changed local link resolves from the containing
file and each fragment names an existing heading. Inspect code-fence balance and
commands, and compare moved instructions for retained constraints. CI checks
changed local links, anchors, reference links and fenced-code balance; it does
not fetch external links or verify that prose and commands are correct.

For any API contract change (not just `schemas.py`), run from the repository root:

```bash
python3 scripts/legacy/extract_openapi.py
cd manager_frontend
npm run gen:api
npm run build
```

Review and commit changed `openapi.json` and `manager_frontend/src/client/` files.
`scripts/sync_manager_api_client.sh` wraps extraction and generation; it does not
perform the required Manager build. The pre-commit hook is a convenience and may
not detect every contract dependency, so it does not replace this obligation.

## Domain workflows

### 1) Product Import Workflow

1. Confirm source parser exists in `parsers/` and is wired in `services/importer_service.py`.
2. Import product(s) through the importer path (Manager/API flow that calls `ImporterService`).
3. Ensure imported specs are normalized through `normalize_specs(...)` in `services/importer_service.py`.
4. Verify created product data (tags, `main_image`, `specs`, `source_url`) in Manager/API.

### 2) Specs Normalization Workflow (New/Updated Keys)

Use this after large catalog imports or when unknown spec keys appear.

1. Analyze unnormalized keys:
   - Docker: `docker compose exec app python3 scripts/analyze_spec_keys.py`
   - Local: `python3 scripts/analyze_spec_keys.py`
2. Extend `SPEC_DEFINITIONS` / `REGISTRY_LEGACY_ALIASES_BY_KEY` in `services/spec_registry.py`; `services/spec_normalizer.py` derives `KEY_MAP` from that registry. Keep value cleanup in the shared normalizer.
3. For local/test data that needs normalization, backfill existing products:
   - Docker: `docker compose exec app python3 scripts/normalize_legacy.py`
   - Local: `python3 scripts/normalize_legacy.py`
4. Re-check output and spot-check product cards/spec rendering in UI.

### 3) Safe Change Verification Workflow

1. Follow [verification by change](#verification-by-change), including API
   generation/build when a contract changes.
2. If specs/import were changed, verify affected fixtures/local test data with:
   - `python3 scripts/analyze_spec_keys.py`
   - `python3 scripts/normalize_legacy.py` (or Docker equivalent)
3. Confirm no obvious regressions in import and public API behavior (no duplicate/product corruption).

### 4) Manager App Workflow

1. Treat `manager_frontend/` as the evolving admin UI for modern workflows.
2. Workflow examples (not an exhaustive feature inventory):
   - convenient product photo editing,
   - bulk editing of product specs,
   - CRM Orders dashboard (B2C/B2B, Kanban/List),
   - Leads funnel (`/api/manager/leads`) with qualification into `Customer + Order`.
3. Future direction:
   - keep expanding manager entities and flows in the Vue-based reactive UX.
4. When API contracts change:
   - update backend schemas/routes and follow [verification by change](#verification-by-change),
   - verify the user flows affected by the changed contract; include photo/spec
     bulk-edit flows when their contracts or shared dependencies are affected.
5. Legacy admin freeze:
   - SQLAdmin routes/views have been removed,
   - avoid adding user workflows under a legacy `/admin` UI,
   - route new UX requirements to manager views first.

### 5) Leads Funnel Workflow

1. Create raw incoming requests as `Lead` (do not create `Customer` directly).
2. Work lead statuses: `new` -> `contacted` -> (`qualified` | `lost` | `spam`).
3. Qualification path:
   - deduplicate customer by `phone/email/inn`,
   - create/update `Customer`,
   - create `Order` with `status=new_lead`, `lead_source=manager`,
   - store `converted_order_id` in `Lead`.
4. Lost/spam lifecycle:
   - excluded from default active lead list,
   - auto-archived after 90 days by scheduler.
5. Orders Kanban shows only real orders; leads stay separate until qualification.
6. For email leads, Manager can review an original PDF, DOCX or DOC service contract on demand. New imports use the private order attachment; older leads without a saved file retrieve the MIME original read-only from IMAP by the order's Message-ID, sender, subject and date. A short-lived in-memory job keeps longer reviews outside HTTP proxy timeouts; its report expires after 30 minutes and is not stored in the order or sent to the customer.
7. Contract review sends extracted text to DeepSeek only after a manager clicks the action. It uses `CONTRACT_REVIEW_MODEL` (default `deepseek-v4-pro`), separately from the platform ZAPRO.SU model and normal `DEEPSEEK_MODEL`. The UI discloses the provider. PDF extraction requires text on every page; DOC/DOCX show a verified clause number or section heading because page numbers are unreliable. Files over 15 MB, PDF over 100 pages and extracted text over 180,000 characters fail explicitly instead of producing a partial review. The original remains available for manual inspection.
8. When a follow-up email belongs to an existing order, a manager can enter the target order number in the inbox and confirm the match. The source email lead remains auditable in the inbox archive, while its private attachments become visible on the target order. The manager can undo the link. A lead with sent documents, sent proposals or payments must be resolved separately. Contract review is available directly from the email card and from an order containing an imported email attachment.

### Native signed PDF copies

The storefront owner uploads private PNG images of the seller's signature and seal under the document legal entity. On a ready native document, the manager opens “Подготовить PDF с подписью и печатью”, places the images directly on the actual PDF pages, and saves a separate `signed_pdf` artifact. Page clicks, mouse/touch dragging, proportional resizing, zoom and keyboard adjustments are supported; signature and seal may be placed on different pages. No numeric coordinates or DOCX markers are needed. Legacy template placements are only initial suggestions; without them, the editor starts on the last page.

The editor uses authenticated, uncached PNG previews rendered by the image's existing Poppler tools. Preview and overlay share the PDF's displayed crop and rotation geometry. Saving validates the source PDF checksum, current PNG IDs and expected signed-copy ID, so a stale edit cannot replace another manager's copy. An issued document's placement can be changed before sending: earlier bytes stay immutable, a new authoritative copy is selected, and the actor, assets and placement are audited. Existing sent/signed copies and closed-order history cannot be replaced. The issued source PDF remains unchanged; replacing either PNG does not automatically rewrite prepared copies. The native PDF download and email attachment path use the current prepared copy when it exists. Check the final PDF visually before sending it.

### Customer-provided order contracts

In the CRM document workspace, select Contract and use the attachment action
beside the contract scenario. Save the customer's contract number and date;
an optional PDF, DOC, DOCX, JPG or PNG can be attached now or later. This records
a one-time order contract without creating a native draft or assigning our own
contract number. Native acts and waybills can select that record as their basis.
Metadata-only registration needs no template or Google connection; source files
use the existing Google Drive upload storage and download in their original
format. Closed-order history and tenant access rules still apply.

## Compose names

`docker-compose.yml` service names include `app`, `db`, `web`, and `bot`
(not `mvn-app`). Check the selected Compose file and profiles before starting
services; the active staff bot is deployed separately, as described in
[bot service boundary](bot-service-boundary.md).
