# AGENTS Guide

Single source of truth for project stack and agent context.
Updated: 2026-02-19.

## Project Scope

- Backend API: FastAPI + SQLModel (`main.py`, `routers/`, `services/`, `crud/`)
- Storefront: Astro + Vue (`web/`)
- Manager UI (primary admin UX): Vue + Vite (`manager_frontend/`)
- Legacy admin: SQLAdmin (`admin/`) maintenance only
- Bot: Aiogram (`bot_app/`)

## Runtime Stack

- Python: 3.12 (Docker base) with async API stack
- API framework: `fastapi==0.128.0`, `starlette==0.50.0`, `uvicorn==0.40.0`
- ORM/data layer: `sqlmodel==0.0.31`, `SQLAlchemy==2.0.45`, `alembic==1.18.1`
- DB drivers: `asyncpg==0.31.0`, `psycopg==3.3.2`, `psycopg2-binary==2.9.11`
- Validation/settings: `pydantic==2.12.5`, `pydantic-settings==2.12.0`
- Admin framework: `sqladmin==0.22.0`
- Bot framework: `aiogram==3.24.0`

## Frontend Stack

### Manager Frontend (`manager_frontend/`)

- Vue `^3.5.24`
- Vite `^7.2.4`
- TypeScript `~5.9.3`
- Tailwind CSS `^3.4.17`
- API client generation: `openapi-typescript-codegen ^0.30.0`
- Generated client location: `manager_frontend/src/client/`

### Storefront (`web/`)

- Astro `^5.16.11`
- Vue `^3.5.27`
- Tailwind CSS `^3.4.19`
- Astro integrations: `@astrojs/vue`, `@astrojs/node`, `@astrojs/mdx`, `@astrojs/sitemap`

## Data and Infrastructure

- Primary DB: PostgreSQL 15 (`postgres:15-alpine`)
- Local orchestration: Docker Compose (`docker-compose.yml`)
- Main services: `app`, `db`, `web`, `bot`, plus `db_test`
- OpenAPI artifact: `openapi.json` in repo root

## API and Contract Workflow

- Manager frontend must call backend through generated client in `manager_frontend/src/client`.
- When API contracts change:
  1. Regenerate OpenAPI: `python3 scripts/legacy/extract_openapi.py`
  2. Regenerate manager client: `cd manager_frontend && npm run gen:api`
  3. Commit changed artifacts (`openapi.json`, `manager_frontend/src/client/*`)

## Test and Build Baseline

- Backend tests:
  - `pytest`
  - `pytest tests/unit -q`
  - `pytest tests/integration -q`
- Storefront build: `cd web && npm run build`
- Manager build: `cd manager_frontend && npm run build`

## Architectural Boundaries

- `routers/`: HTTP layer only (validation, wiring, response models)
- `services/`: business logic
- `crud/`: DB access and query logic
- New admin UX/features: manager-first (`manager_frontend/` + `routers/manager_*`)
- Legacy SQLAdmin: compatibility and bugfixes only

## Notes for Agents

- Prefer targeted, minimal changes.
- Do not implement new business features in legacy admin unless explicitly requested.
- Keep generated API client in sync with backend schemas/routes.
