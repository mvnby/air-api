# **🤘 The Lowdown on the AI Agent Project**

## **What's the Vibe?**

So, we're building this wicked **Air Conditioning Management System**. It's got a Telegram Bot for the users and a killer Admin Panel for us.

Running on modern Python async goodness (fast af 🚀). Still baking it, but it's getting there.

## **Current Mission: Headless Commerce & Store Infrastructure**

We are transitioning from a pure internal CRM/Bot system to a full **Headless Commerce Backend**. 
The API is ~80% ready for the upcoming **Astro JS + Vue.js** store.

### **Upcoming Objectives:**
1. **Media Engine**: Implement robust image processing, storage, and linking (Products ↔ Images ↔ Articles).
2. **Production Core**: Set up automated DB backups & restoration.
3. **Smooth Ops**: Implement a reliable deployment/update flow (Local → Production).
4. **Store UI**: Building the web vitrine with Astro and interactive Vue components.

## **The Tech Stack (The Good Stuff)**

### **Backend ⚙️**

* **Lang:** Python 3.10+ (only the fresh stuff).  
* **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Zoom zoom!).  
* **Server:** Uvicorn (running inside Docker).
* **DB:** [PostgreSQL 15](https://www.postgresql.org/) (Running in Docker).
* **Driver:** `postgresql+asyncpg://` for async API and `psycopg2` for sync tasks (like migration).
* **ORM:** [SQLModel](https://sqlmodel.tiangolo.com/) (SQLAlchemy wrapped up nice).  
* **HTTP:** httpx (async requests ftw).
* **Infra:** [Docker Compose](https://docs.docker.com/compose/) (Everything's containerized!).

### **Admin UI 👨‍💻**

* **Framework:** [SQLAdmin](https://aminalaee.dev/sqladmin/).  
* **Auth:** HTTP Basic Auth + Session-based (Phase 29).  
* **Customs:** Check admin/ for our custom views.  
* **Frontend:** Just some vanilla JS via extra_js. Keepin' it old school.

### **Telegram Bot 🤖**

* **Framework:** [Aiogram 3.x](https://docs.aiogram.dev/en/latest/) (Async only!).  
* **Home:** bot_app/ and bot.py.  
* **State:** aiogram.fsm (like ShopState).

## **How We Built It (Architecture)**

We stick to a strict **Service-Layer** setup. No shortcuts!

1. **Routers/Admin/Bot:** They just take input, call a Service, and spit out output. **NO DB ACCESS HERE!** Don't even think about it.  
2. **Services (services/):** The brains. Business logic & transactions live here.  
3. **CRUD (crud/):** Just talking to the DB.  
4. **Models (models.py):** Data shapes.

**Key Folders:**

* /services:  
  * order_service.py: Orders & items logic.  
  * cart_service.py: Shopping cart & checkout flow.  
  * google_service.py: Google API wrapper. **Features:** OAuth 2.0 (bye service acct), "Double Reverse" table fill (cool hack), Merging cells & Styling.  
  * document_service.py: Prepping data for Contracts/Offers.  
* /crud: DB access objects.  
* /admin: The UI views.
* /core: Config, database, logging, **security** (Phase 29).

## **Hall of Fame (History)**

* ... (Old stuff 1-24) ...  
* **Phase 26**: Refactored the architecture. Moved Order logic to Services. Cleaned house.  
* **Phase 27**: **Shopping Cart**. Cart model, Service, and Checkout flow are LIVE.  
* **Phase 28**: **Google Docs Automation (BIG W)**.  
  * **OAuth 2.0**: Switched to User Auth (token.json) cuz service account quotas are trash (we need that 2TB storage).  
  * **Fancy Tables**: Implemented "Double Reverse" insertion so indexes don't break. Genius move.  
  * **Pro Styling**: Added a "Total" row with **merged cells**, right align, and bold text. Looks pro.  
  * **B2B Logic**: Added CustomerType (Individual/Company), bank details, and num2words to write out sums.  
  * **Templates**: Contract, Invoice, Offer supported.
* **Phase 29**: **Security & Authentication (LOCKED DOWN)**.  
  * **HTTP Basic Auth**: Protected all admin endpoints with credentials from .env.  
  * **SQLAdmin Auth**: Custom AuthenticationBackend with session-based login/logout.  
  * **Timing Attack Protection**: Using secrets.compare_digest() for credential checks.
* **Phase 4**: **Nakladnaya (Waybill) & Act Improvements**.
  * **Waybills (TN-2/TTN-1)**: Implemented specialized Belarusian documents with strict column merging (Rate=R, Sum=S-T) and sparse mapping logic.
  * **Act Generation**: Added date, total services, and total words calculation.
  * **Stability**: Fixed 500 errors by initializing variables properly.
  * **Table Logic**: Switched to "Insert Row + Delete Placeholder" strategy for cleaner output.
* **Phase 5**: **Web UI Token Management (No more console hacks)**.
  * **OOB Auth Flow**: Implemented "Copy Link -> Paste Code" flow for Google Auth directly in Admin UI.
  * **Admin Integration**: Added dedicated view to check token expiration and regenerate it.
* **Phase 6**: **Operational Dashboard (Command Center)**.
  * **Real-time Stats**: Connected Frontend to Backend. "Active on Site", "Latest Orders", "Latest Products" now show live data.
  * **Action Items**: Added "Overdue Assessments" and "Upcoming Installations" alerts.
  * **UI Fixes**: Solved `undefined` widgets and AJAX loading issues.
* **Phase 7**: **Automation & Notifications**.
  * **Stalled Deals**: Auto-tracking of "stuck" deals >14 days.
  * **Notification Bot**: Installers get Telegram alerts for new jobs.
  * **Installer Management**: Inline editing of installers, pay tracking, and eager-loading bug fixes in Admin.
* **Phase 8**: **Resource Calendar**.
  * **Visual Schedule**: FullCalendar.js integration.
  * **Conflict Avoidance**: See dates for Installation/Assessment.
* **Phase 30**: **PostgreSQL & Docker (MODERN ERA)**.
  * **DB Migration**: Switched from SQLite to Postgres for reliability.
  * **Dockerization**: The whole stack (API, Bot, DB) now runs via Docker Compose.
  * **Requirements Upgrade**: Added `pydantic-settings`, `asyncpg`, `psycopg2-binary`.
  * **Logging Fix**: Updated `setup_logging` to be more flexible for multi-service context.
* **Phase 31**: **Advanced Document Generation & Contract UX**.
  * **Contract Placeholders**: Implemented `{{contract_name}}` and `{{contract_date}}` for all documents (Acts, TN-2, Invoices).
  * **Pre-generation Numbering**: Refactored `DocumentService` to generate document numbers *before* creation, allowing documents (like contracts) to reference their own ID.
  * **Automatic Totals Calculation**: Fixed critical bug where `total_amount` stayed 0. Added `calculate_totals()` with explicit relationship loading (`selectinload`) during every order update in Admin.
  * **UX Improvements**: Removed manual `contract_number` input (now auto-generated from `OrderDocument`) and added optional `contract_date` with default=today for manual "backdating" if requested by client.
* **Phase 32**: **Headless Commerce API & SEO Slugs**.
  * **SEO-friendly Slugs**: Implemented brand-model URL generation (`chigo-cs51...`) and migration scripts.
  * **Public API v1**: Added `/catalog`, `/products/{slug}`, `/content/articles/`, and `/orders` endpoints for guest users.
  * **Refactoring & Logging**: Extracted response mapping logic, added pagination validation, and replaced print() with the `logging` module for production traceability.


## **The Rules (Don't Break These) 🚨**

1. **Service Layer Only**: Seriously, no raw SQL in routers or admin. I will find you.  
2. **Sessions**: Always new session when calling Services from Admin: async with async_session_maker() as session: ....  
3. **Google Stuff**:  
   * Use client_secret.json to get token.json.  
   * **NEVER commit these secrets to Git.** Instant fail if you do.  
   * Templates need a 1-row header table to work.
4. **Security (Phase 29)**:  
   * **Credentials in .env**: ADMIN_USERNAME and ADMIN_PASSWORD. Never hardcode.  
   * **Protect Admin Endpoints**: Use `Depends(get_current_username)` for HTTP Basic Auth.  
   * **AJAX from Admin Panel**: Use `Depends(check_admin_session)` for session-based auth.  
   * **Public API**: Keep /api/products, /api/health, etc. open for the bot.

## **Git Life**

1.  **No pushing to main.** Ever.  
2.  New feature? git checkout \-b feature/phase-NAME.  
3.  Push it and PR it.

## **Cheat Sheet**

*   **Fire it up:** `docker compose up -d --build`
*   **Check logs:** `docker compose logs -f`
*   **Kill it:** `docker compose down`
*   **Migrate DB:** `docker compose exec app python scripts/migrate_sqlite_to_pg.py`
*   **Get Google Token:** `python scripts/get_token.py` (Run inside container if needed)