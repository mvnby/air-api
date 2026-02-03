# Project Architecture & Status

**Application**: Air Conditioning Management System (E-commerce + CRM + Admin + Bot)
**Architecture**: Headless Commerce (FastAPI Backend + Astro/Vue Frontend)
**Infrastructure**: Docker Compose, PostgreSQL

## 1. Technical Stack

### Backend (API)
- **Framework**: FastAPI (Async)
- **Database**: PostgreSQL 15 (Async `asyncpg` + `SQLModel`/`SQLAlchemy`)
- **Authentication**: HTTP Basic (Admin) + Session-based (SQLAdmin)
- **Services**: Telegram Bot (`aiogram` 3.x), Google Sheets Integration (OAuth 2.0)

### Frontend (Web)
- **Framework**: Astro 4.x (SSR + Static)
- **Interactivity**: Vue 3 (Composition API)
- **Styling**: TailwindCSS + Vanilla CSS Variables
- **State Management**: Nanostores (Persistent Cart)

### Infrastructure
- **Containerization**: Docker Compose (`web`, `api`, `bot`, `db`)
- **Reverse Proxy**: Nginx (Production) / Direct exposed ports (Dev)

## 2. Current Mission: Production Readiness & Feature Expansion

**Status**: Active Development
- **Storefront**: Live (Headless, Premium Design)
- **Backoffice**: Feature-rich Admin Panel
- **Bot**: Operational for notifications and search

### Upcoming Objectives
1. **Media Engine**: Implement local image serving (`/media/`) to deprecate external URLs.
2. **Production Core**: Automated DB backups and restoration workflows.
3. **Deployment**: Finalize CI/CD pipelines.

## 3. Architectural Evolution (Key Decisions Log)

* **Phase 26 (Architecture)**: Transitioned to **Service Layer Pattern**. Logic moved from Routers to `services/`.
* **Phase 27 (Commerce)**: Implemented Shopping Cart and Checkout flow.
* **Phase 28 (Integrations)**: Google Docs automation for Contracts/Invoices using "Double Reverse" table insertion and OAuth 2.0.
* **Phase 29 (Security)**: Implemented dual authentication (HTTP Basic for API, Sessions for Admin).
* **Phase 30 (Database)**: Migrated from SQLite to **PostgreSQL**. Full Dockerization.
* **Phase 32 (Headless)**: Decoupled Frontend/Backend. Introduced Public API v1 (`/api/v1/`). Implemented SEO-friendly slugs.
* **Phase 33-34 (UI)**: Adopted "Master Vozduha" Brand Identity. Created reusable `ProductCard` with toggle logic.
* **Phase 35 (Security)**: Hardened CORS with managed origins whitelist.
* **Phase 36 (State)**: Implemented Persistent Cart using `nanostores`.
* **Phase 37 (Pricing)**: **Snapshot Pricing Pattern**. Service details (price/title) are copied to `OrderServiceLink` at checkout time to prevent historical data mutation.
* **Phase 39 (Service-Only)**: Architected "Installation Only" orders (no physical product). Handled via `OrderServiceLink`.
* **Phase 40 (Rich Options)**: Enhanced Installation Calculator. Services now support rich metadata (images, slugs) and are split into distinct line items in orders.
* **Phase 41 (Infrastructure)**: Fixed PostCSS/Tailwind build pipeline in Docker.
* **Phase 42 (Content)**: Implemented MDX Blog Engine. Added Content Collections, Reading Time, and Related Articles.
* **Phase 43 (Network/Optimization)**: Unified API Client (`/api/v1` default). Optimized Network Layer (dynamic SSR/Client base URL). Removed legacy hardcoded URLs. Integrated real-time price refreshing in Cart.
* **Phase 44 (Backup System)**: Upgraded `BackupService` to archive media (`.tar.gz`). Implemented automated Google Drive rotation (last 20 files). Strict daily scheduling at 3:00 AM.
* **Phase 45 (SEO & Marketing)**: Implemented complete SEO package: Sitemap, dynamic Meta Tags, Open Graph visuals, and JSON-LD structured data. Integrated Google Tag Manager (GTM). Hardened `Layout` with robust script injection.
* **Phase 46 (Smart Checkout)**: Implemented B2B "Smart Checkout". Added `imask` phone masking (+375). Created public proxy endpoints (`/v1/proxy/egr`, `/v1/proxy/bank`) for secure, unauthenticated auto-fill of Organization names and Bank details. Updated `Customer` model to persist B2B data (`UNP`, `IBAN`, `BIC`).
* **Phase 47 (Manager Tools)**: Implemented a dedicated Manager Dashboard (`/manager`). Features include DuckDuckGo image search integration, one-click WebP conversion/upload, and "Find Image" workflow for products. Solved 500 errors by switching to `ddgs` and fixed persistence issues with explicit SQL updates.
* **Phase 48 (Manager Polish)**: Enhanced Manager Dashboard with **Gallery Management** (add/delete/promote), **Reuse from Catalog** tool, and reactive UI updates. Replaced `window.confirm` with custom UI. Validated dual-storage strategy: `gallery_images` (relation) as source of truth. Added **Local Image Upload** (Drag & Drop + Multi-select) via `POST /upload-local-images`. Fixed Media Storage conflict (consolidated to root `media`). Enabled auto-tagging for Unit Types (Wall/Duct/etc). ensured absolute URLs in API for Manager App consistency.
* **Phase 49 (Stabilization)**: Paused feature development to pay down technical debt. Implemented **Pytest Infrastructure** with isolated `db_test` container. Migrated legacy scripts to unit/integration tests. Integrated **Sentry** SDK for monitoring. Introduced **OpenAPI Codegen** for Frontend, replacing manual fetch calls with a generated, type-safe Client (`manager_frontend/src/client`). Fixed critical schema bugs in `OrderService` and `Product` models.

1.  **Service Layer Pattern**: NEVER write raw SQL or business logic in Routers/Admin views. Always use `services/`.
2.  **Session Management**: Always instantiate a new session when calling services from the Admin panel:
    ```python
    async with async_session_maker() as session:
        # call service
    ```
3.  **Authentication**:
    -   Admin Endpoints: `Depends(get_current_username)`
    -   Admin Actions (AJAX): `Depends(check_admin_session)`
    -   Public API: Open access (e.g., `/api/products`).
4.  **Security**:
    -   **Secrets**: `client_secret.json` / `token.json` MUST be in `.gitignore`.
    -   **Env Vars**: Use `ADMIN_USERNAME`/`ADMIN_PASSWORD` from `.env`.
    -   **CORS**: strict whitelist via `CORS_ORIGINS`.

## 5. Git Workflow

1.  **Main Branch Protected**: Never push directly to `main`.
2.  **Feature Branches**: `git checkout -b feature/phase-NAME`
3.  **Process**: Commit -> Push -> Pull Request.

## 6. Operational Commands (Cheat Sheet)

-   **Start Stack**: `docker compose up -d --build`
-   **Logs**: `docker compose logs -f [service_name]`
-   **Stop**: `docker compose down`
-   **Generate Google Token**: `python scripts/get_token.py` (run inside container or venv)

## 7. Knowledge Base & Lessons

1.  **API Versioning & Routing**:
    -   Backend: `/api` for internal/legacy, `/api/v1` for Headless Public API.
    -   Frontend: When fetching by ID, ensure the URL path is correct (strip `/v1` if legacy endpoint needed).
2.  **SSR Networking**:
    -   Server-Side (Astro): Connects to `http://api:8000` (Docker internal DNS).
    -   Client-Side (Browser): Connects to `http://localhost:8000` (or production domain).
3.  **Snapshot Pricing**:
    -   Changing a global service price does NOT affect existing orders.
    -   Logic relies on `OrderServiceLink` having its own `price` and `title` fields.
4.  **Blog Content**:
    -   Located in `web/src/content/blog/`.
    -   Must use `.mdx`.
    -   Images: `web/public/img/blog/` (referenced as `/img/blog/...`).