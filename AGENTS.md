# AGENTS Guide

This file defines practical workflows and commands for contributors and coding agents in this repo.

## Project Layout

- Backend API: FastAPI + SQLModel (`main.py`, `routers/`, `services/`, `crud/`)
- Frontend storefront: Astro + Vue (`web/`)
- Admin: SQLAdmin custom views (`admin/`)
- Manager app (future primary admin UI on Vue + FastAPI): `manager_frontend/`
- Tests: `tests/unit/`, `tests/integration/`
- Data/import utilities: `scripts/`

## Core Rules

- Keep service-layer boundaries:
  - `routers/` and `admin/` should not contain direct DB business logic.
  - business logic belongs in `services/`.
  - persistence access belongs in `crud/`.
- Reuse existing normalization logic in `services/spec_normalizer.py` instead of duplicating key/value cleanup.
- Prefer small, targeted changes and run relevant tests/scripts before handoff.
- Manager-first policy:
  - New product functionality must be implemented in `manager_frontend/` + `routers/manager_*`.
  - Legacy SQLAdmin (`admin/`) is compatibility-only: bugfixes, regressions, and required maintenance.
  - Do not introduce net-new business features in legacy admin unless explicitly approved.

## Commands

Run from repo root unless noted.

### Environment and App

- Start stack (API + DB + web): `docker compose up -d`
- Stop stack: `docker compose down`
- API logs: `docker compose logs -f app`
- Open API locally: [http://localhost:8000/docs](http://localhost:8000/docs)
- Open web locally: [http://localhost:4321](http://localhost:4321)

### Backend Tests

- Run all tests (local venv): `pytest`
- Run unit tests only: `pytest tests/unit -q`
- Run integration tests only: `pytest tests/integration -q`

### Frontend (Astro)

Run from `web/`:

- Install deps: `npm install`
- Dev server: `npm run dev`
- Build (includes API pre-check): `npm run build`
- Preview build: `npm run preview`
- API readiness check only: `npm run check-api`

### Manager Frontend (Vue)

Run from `manager_frontend/`:

- Install deps: `npm install`
- Dev server: `npm run dev`
- Build: `npm run build`
- Preview build: `npm run preview`
- Regenerate API client from backend OpenAPI: `npm run gen:api`
  - Note: this project uses `--useUnionTypes` in codegen to avoid TS enum re-export issues.

## Workflows

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
2. Extend mapping in `services/spec_normalizer.py` (`KEY_MAP` + value cleanup rules if needed).
3. Backfill existing products:
   - Docker: `docker compose exec app python3 scripts/normalize_legacy.py`
   - Local: `python3 scripts/normalize_legacy.py`
4. Re-check output and spot-check product cards/spec rendering in UI.

### 3) Safe Change Verification Workflow

1. Run scoped tests for touched area (`pytest ...`).
2. If API routes, operation IDs, or schemas in `schemas.py` were changed, run:
   - `python3 scripts/legacy/extract_openapi.py && cd manager_frontend && npm run gen:api`
3. If specs/import were changed, run:
   - `python3 scripts/analyze_spec_keys.py`
   - `python3 scripts/normalize_legacy.py` (or Docker equivalent)
4. For frontend changes in `web/`, run `npm run build` in `web/`.
5. Confirm no obvious regressions in:
   - product list and product page spec rendering,
   - import path behavior (no duplicate/product corruption).

### 4) Manager App Workflow (Current + Future)

1. Treat `manager_frontend/` as the evolving admin UI for modern workflows.
2. Current implemented focus:
   - convenient product photo editing,
   - bulk editing of product specs,
   - CRM Orders dashboard (B2C/B2B, Kanban/List),
   - Leads funnel (`/api/manager/leads`) with qualification into `Customer + Order`.
3. Future direction:
   - migrate broader admin entities and flows from legacy SQLAdmin UX to Vue-based reactive UX.
4. When API contracts change:
   - update backend schemas/routes,
   - regenerate OpenAPI (`python3 scripts/legacy/extract_openapi.py`),
   - refresh typed client with `npm run gen:api` in `manager_frontend/`,
   - commit generated artifacts (`openapi.json`, `manager_frontend/src/client/*`) when changed,
   - verify photo/spec bulk-edit flows end-to-end.
5. Legacy admin freeze:
   - keep SQLAdmin routes/views working for existing operations,
   - avoid adding new user workflows there,
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

### 6) Prod Data Ops Without Git

Production server intentionally runs from Docker images only (no git checkout in `/opt/air-api`).

1. Trigger path:
   - Backend deploy pulls `ghcr` image and recreates `app`/`bot`.
   - Optional post-deploy ops run via `scripts/ops_post_deploy.sh`.
2. Safe defaults:
   - `OPS_MODE=report_only`
   - `RUN_NORMALIZE_LEGACY=false`
   - `RUN_CLEANUP_LEGACY_LINKS=false`
   - `RUN_REPORT_LEGACY_LINKS=true`
   - `DRY_RUN=true`
3. Manual commands on prod:
   - Report only:
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/report_legacy_tag_links.py`
   - Normalize:
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/normalize_legacy.py`
   - Cleanup dry-run:
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/cleanup_legacy_tag_links.py`
   - Cleanup execute (manual-only):
     - `docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app python3 scripts/cleanup_legacy_tag_links.py --execute`
4. Policy:
   - Cleanup is manual and explicit only.
   - Post-deploy smoke-check must pass (`/health`, `/api/v1/products?limit=5`, `/api/v1/filters/config`) before considering deploy successful.

## Notes

- `docker-compose.yml` service names are `app`, `db`, `web`, `bot` (not `mvn-app`).
- `scripts/normalize_legacy.py` uses shared normalization logic from `services/spec_normalizer.py`; keep both in sync.
- Legacy admin (`admin/`, SQLAdmin) and manager app (`manager_frontend/`, Vue) currently coexist; prefer implementing new rich admin UX in manager app.
- Manager list endpoints enforce pagination limits (`limit <= 100`); keep frontend requests within this bound.
