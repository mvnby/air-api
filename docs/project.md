# **🤘 The Lowdown on the AI Agent Project**

So, we're building this wicked **Air Conditioning Management System**. It's got a Telegram Bot for the users and a killer Admin Panel for us.

Running on modern Python async goodness (fast af 🚀). Still baking it, but it's getting there.

## **Current Mission: Production Readiness & Feature Expansion**

We have successfully transitioned to a **Headless Commerce** architecture. The **Astro JS + Vue.js** storefront is implemented with a premium brand design.

### **Upcoming Objectives:**
1. **Media Engine**: Implement robust local image processing (via `/media/`) to replace external links.
2. **Production Core**: Set up automated DB backups & restoration.
3. **Smooth Ops**: Finalize the production deployment pipeline.

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
* **Phase 33**: **Premium Storefront UI & Branding**.
  * **Brand Identity**: Integrated new "МАСТЕР ВОЗДУХА" teal logo and color system.
  * **UI Redesign**: Re-implemented Home, Catalog, and Product sections in Astro with the "Google Stitch" premium aesthetic.
  * **Design System**: Established [ui.md](file:///Users/maksimkorotov/dev/mvn/docs/ui.md) guide with specific spacing, typography, and theme-switching logic.
  * **Fixes**: Cleaned up logo backgrounds and established transparent asset pipeline.

* **Phase 34**: **Product Card Component & Catalog Refactor**.
  *   **Reusable Component**: Created `ProductCard.astro` with "Default", "Hero", and "Minimal" variants.
  *   **Features**: Integrated "Installation Toggle" logic directly into the component.
  *   **UI Polish**: Premium "Squircle" design, row-based badges, and optimized layout.
  *   **Refactor**: Updated Home and Catalog pages to use the new component, ensuring design consistency.
  *   **Fixes**: Solved SSR API versioning issues in `api.js` and fixed badge duplication.
  *   **Feature**: Added slug classes to feature tags for custom styling.
  
* **Phase 35**: **CORS Hardening (SECURITY BOOST)**.
  * **Strict Policy**: Replaced wildcard `["*"]` with a managed whitelist.
  * **Managed Origins**: Origins are now configurable via `CORS_ORIGINS` in `.env`.
  * **Defaults**: Pre-configured with `https://mvn.by`, `https://dev.mvn.by`, and local dev ports.

* **Phase 36**: **Shopping Cart & Robust Checkout**.
  * **Persistent Store**: Implemented `nanostores` based cart persisting to localStorage.
  * **UI Components**: Created `CartPage`, `CheckoutForm`, and `HeaderCart` badge.
  * **Smart Add-to-Cart**: Integrated `PriceWithToggle` to handle installation options and price calculations.
  * **Auto-Repair Logic**: Implemented fallback mechanism in Checkout to resolve missing Product IDs by slug (handling stale cart data gracefully).
  * **New Pages**: `/cart`, `/checkout`, `/success` fully implemented.

* **Phase 37**: **Snapshot Pricing & Installation Refactor (ARCHITECTURE STABILITY)**.
  * **Decoupled Pricing**: Successfully transitioned to "Snapshot Pricing" pattern where service details (title, price) are stored directly in the order.
  * **Flexible DB Schema**: Migrated `service_id` to be nullable in `OrderServiceLink`, allowing for custom services not bound to the `services` table.
  * **Automated Logic**: Implemented detailed auto-generation of installation titles during checkout (e.g., "Стандартный монтаж кондиционера мощностью 3.5 кВт...").
  * **Admin UI Cleanup**: Removed confusing/redundant installation checkboxes from the products table; everything is now unified under the "Services" section with editable titles.
  *   **Contract Ready**: Updated document engine (Contracts, Acts, Invoices) to prioritize snapshot titles for 100% accuracy in generated files.
  
* **Phase 38**: **Cart Redesign & UX Polish**.
  * **Layout Standardization**: Unified Cart and Checkout pages with a reliable side-by-side grid layout (sticky summary sidebar) for desktop, stacking correctly on mobile.
  * **Dark Mode Logic**: Fixed styling issues in Vue components (`CartPage`, `CheckoutForm`) using CSS variables for robust theme support.
  * **Interactive Feedback**: Implemented "Morphing Buttons" (Add -> Check) and global Toast notifications for clear user confirmation.
  * **Bug Fixes**: Resolved critical Vue hydration issues (nesting bugs) using explicit keys and fixed catalog badge overlaps.

* **Phase 39**: **Standalone Installation Calculator & Advanced Cart**.
  * **Service-Only Orders**: Architected system to support orders without physical products (Installation Only). Refactored backend to store these as `OrderServiceLink` for correct admin logic.
  * **Detailed Metadata**: Implemented smart title generation for services (e.g., "Installation (Wall) Power < 3.5kW, Pipe 5m") improving clarity for admins and documents.
  * **Advanced Cart**: Enhanced Cart Store and UI to allow per-item installation configuration (Pipe meters, Options) directly in the cart before checkout.
  * **Calculator UX**: Added "Order Service" modal to the Installation Calculator, allowing direct lead generation from the tools page.
  * **Notification Upgrade**: Updated Telegram Admin alerts to support and clearly display standalone service orders.

* **Phase 40**: **Rich Installation Options & Robust Orders (DATA INTEGRITY)**.
  * **Rich Services**: Repurposed `services` table to store installation add-ons with detailed metadata (Image, Description, Slug).
  * **Admin UI**: Updated `ServiceAdmin` to support image uploads and rich text fields for add-ons.
  * **Frontend Integration**: Updated Cart to fetch and display rich installation options dynamically.
  * **Order Logic**: Rewrote `create_from_website` to split "Installation" into distinct `OrderServiceLink` items (Main Installation + Individual Add-ons).
  * **Title Formatting**: Implemented robust Russian title generation for installation services (e.g., "Монтаж кондиционера настенного типа, мощностью до 4 кВт...").
  * **Bug Fixes**: Solved backend crash (Lazy Loading recursion), CORS issues, and fixed a critical bug where installation discounts were lost during option updates.
  * **Rich Service Calculator (Part 2)**: 
    * **Grid UI**: Replaced the simple calculator with a modern CSS Grid layout featuring "Rich Options" (images, descriptions, selection states).
    * **Service Splitting**: Enhanced the calculator's backend flow to split selected options into separate `OrderServiceLink` line items for the admin panel and Telegram notifications.
    * **Integration**: Fully integrated with the `installationStore` and verified data integrity across the entire order creation pipeline.
* **Phase 41**: **Professional Content & Stable Infrastructure (COMPLETE)**.
  * **Infrastructure Fix**: Resolved critical Tailwind CSS processing issues by configuring PostCSS and `autoprefixer` within the Docker build pipeline.
  * **Stability**: Fixed "everything went down" deployment failure by forced cache-clearing rebuild of the `web` container.
  * **Content Collections**: Migrated blog articles to the correct Astro Content Collection system (`/src/content/blog/`), fixing `getCollection` errors.
  * **Premium Components**: Implemented MDX-compatible components: `CallToAction.vue` (Glassmorphism, animations) and `WarningBlock.vue` (unified dark mode styling).
  * **UI/UX Refinement**: Optimized `ArticleLayout.astro` with better header spacing (`pt-24/32`), teal gradients for headings, and high-resolution local images for technical articles.
  * **IDE Polish**: Resolved "Unknown at rule @tailwind" linting errors in VS Code via `settings.json` and custom CSS data.

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
   * **CORS Management**: Use `CORS_ORIGINS` in `.env` for production domain control. No more `*` allow-all.

## **Git Life**

1.  **No pushing to main.** Ever.  
2.  New feature? git checkout \-b feature/phase-NAME.  
3.  Push it and PR it.

## **Cheat Sheet**

*   **Fire it up:** `docker compose up -d --build`
*   **Check logs:** `docker compose logs -f`
*   **Kill it:** `docker compose down`
*   **Get Google Token:** `python scripts/get_token.py` (Run inside container if needed)

## **Technical Context & Lessons**

1.  **API Versioning**:
    *   `/api/products/{id}` -> Get by ID.
    *   `/api/v1/products/{slug}` -> Get by Slug (Headless V1).
    *   *Lesson*: When fetching by ID in frontend, strip `/v1` from base URL if necessary.
2.  **Docker Commands**:
    *   Use `docker compose` (v2 style), NOT `docker-compose`.
    *   To restart a specific service: `docker compose restart web`.
    *   **SSR Networking**: URLs like `localhost:8000` inside a container point to the container itself. Use service names (e.g., `http://app:8000`) for internal communication.