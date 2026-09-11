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

- Run all tests (local venv): `pytest`
- Run unit tests only: `pytest tests/unit -q`
- Run integration tests only: `pytest tests/integration -q`
- Prove physical PostgreSQL isolation for two future pytest workers:
  `pytest -q -n 2 --dist load tests/integration/test_postgres_worker_database_isolation.py`

PostgreSQL test policy:

- Every pytest process/xdist worker derives and owns a separate physical
  database from `TEST_DATABASE_URL`.
- Do not point `PYTEST_BASE_DATABASE_URL` at a production database. The test
  bootstrap rejects base database names without a `test` marker.
- Keep broad unit/integration suites serial until worker-isolation proof and
  timing evidence are green in CI; enable xdist per suite as a separate change.

### Manager Frontend (Vue)

Run from `manager_frontend/`:

- Install deps: `npm install`
- Dev server: `npm run dev`
- Build: `npm run build`
- Preview build: `npm run preview`
- Regenerate API client from backend OpenAPI: `npm run gen:api`
  - Note: this project uses `--useUnionTypes` in codegen to avoid TS enum re-export issues.

## Domain workflows

### 1) Product Import Workflow

1. Confirm source parser exists in `parsers/` and is wired in `services/importer_service.py`.
2. Import product(s) through the importer path (API/admin flow that calls `ImporterService`).
3. Ensure imported specs are normalized through `normalize_specs(...)` in `services/importer_service.py`.
4. Verify created product data (tags, `main_image`, `specs`, `source_url`) in admin/API.

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

1. Run scoped tests for touched area (`pytest ...`).
2. If API routes, operation IDs, or schemas in `schemas.py` were changed, run:
   - `python3 scripts/legacy/extract_openapi.py && cd manager_frontend && npm run gen:api`
3. If specs/import were changed, verify affected fixtures/local test data with:
   - `python3 scripts/analyze_spec_keys.py`
   - `python3 scripts/normalize_legacy.py` (or Docker equivalent)
4. Confirm no obvious regressions in import and public API behavior (no duplicate/product corruption).

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
   - update backend schemas/routes,
   - regenerate OpenAPI (`python3 scripts/legacy/extract_openapi.py`),
   - refresh typed client with `npm run gen:api` in `manager_frontend/`,
   - commit generated artifacts (`openapi.json`, `manager_frontend/src/client/*`) when changed,
   - verify photo/spec bulk-edit flows end-to-end.
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

## Compose names

`docker-compose.yml` service names include `app`, `db`, `web`, and `bot`
(not `mvn-app`). Check the selected Compose file and profiles before starting
services; the active staff bot is deployed separately, as described in
[bot service boundary](bot-service-boundary.md).
