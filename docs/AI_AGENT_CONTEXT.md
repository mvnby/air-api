# **🤘 The Lowdown on the AI Agent Project**

## **What's the Vibe?**

So, we're building this wicked **Air Conditioning Management System**. It's got a Telegram Bot for the users and a killer Admin Panel for us.

Running on modern Python async goodness (fast af 🚀). Still baking it, but it's getting there.

Current Mission: Stabilize & Ship It.  
We just crushed the Shopping Cart (Phase 27), totally nailed the Google Docs Automation (Phase 28) with some fancy table magic, and now we've locked down the system with HTTP Basic Auth (Phase 29).

## **The Tech Stack (The Good Stuff)**

### **Backend ⚙️**

* **Lang:** Python 3.10+ (only the fresh stuff).  
* **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Zoom zoom!).  
* **Server:** Uvicorn (boss it around via ./manage.sh).  
* **DB:** SQLite air_conditioners.db driven by aiosqlite. Simple & clean.  
* **ORM:** [SQLModel](https://sqlmodel.tiangolo.com/) (SQLAlchemy wrapped up nice).  
* **HTTP:** httpx (async requests ftw).

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
* **Phase 8** (Next): **Resource Calendar**.
  * **Visual Schedule**: FullCalendar.js integration.
  * **Conflict Avoidance**: See dates for Installation/Assessment.


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

1. **No pushing to main.** Ever.  
2. New feature? git checkout \-b feature/phase-NAME.  
3. Push it and PR it.

## **Cheat Sheet**

* **Fire it up:** ./manage.sh start  
* **Kill it:** ./manage.sh stop  
* **Get Google Token:** python scripts/get\_token.py