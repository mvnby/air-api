# CRM Gap Analysis & Progress Report

**Date:** 2026-01-18  
**Based on:** `CRM для кондиционеров_ Анализ и Проектирование.md`

## 1. Executive Summary
The CRM implementation is **advanced and highly aligned** with the initial architectural design (~85% complete). The core data structure, Admin UI (including Kanban), and financial logic are fully operational. The primary gaps are in **automation** (dealing with stalled deals) and **integration** (notifying installers via Telegram).

## 2. Component Analysis

### ✅ Data Model (100% Complete)
The database schema (`models.py`) is a near-perfect match to the design:
- **Order Structure:** Implemented with `technical_meta` (JSON), `total_amount`, `margin`.
- **Snapshot Pricing:** `OrderProductLink` fixes `price` and `cost` at the moment of sale.
- **Installers:** `OrderInstaller` supports `agreed_pay` (job-specific rates) and `role`.
- **Statuses:** Full `OrderStatus` enum is implemented correctly.

### ✅ Admin Interface (90% Complete)
- **Kanban Board:** Backend logic (`admin/kanban.py`) is implemented. **UI Verification:** Confirmed functional drag-and-drop interface with correct columns (New Lead -> Assessment -> Proposal).
- **Order Management:** `OrderAdmin` includes status coloring and custom search/filtering. **UI Verification:** Clean list view, functional CRUD forms.
- **Inventory Safety:** The specific logical check (`stock < 3` alert on Proposal) is implemented in `on_model_change`.
- **Dashboard:** The backend service (`analytics_service.py`) calculates metrics.
    - ⚠️ **UI Issues:** Browser analysis revealed bugs in the Dashboard template:
        - "Active on Site" widget shows `undefined`.
        - "Latest Orders" table is stuck on "Loading..." state.
        - "Latest Products" table is empty (visual bug or data issue).

### ⚠️ Business Logic & Automation (60% Complete)
- **Document Generation:** **Implemented (Alternative Approach).** Instead of local PDF (WeasyPrint), the system uses Google Docs/Sheets API (`document_service.py`). This allows for easier template editing but requires internet access. It covers all key docs (Quote, Work Order, Invoice).
- **Inventory Reservation:** Implemented via `OrderStatus` logic.
- **MISSING: Stalled Deal Automation:** The design called for automatically marking deals as `deferred` or sending alerts if they stay in `negotiation` > 7 days. The `scheduler_service.py` currently only syncs prices.
- **MISSING: Installer Notifications:** While `bot_app` exists, there is no explicit link sending a Telegram message to an installer when they are assigned to an `Order`.

## 3. Gap Analysis Table

| Feature | Design Requirement | Current Status | Validation |
| :--- | :--- | :--- | :--- |
| **Pipeline Stages** | 7 Distinct Stages | ✅ Implemented | `OrderStatus` enum |
| **Snapshot Pricing** | Store cost/price at sale | ✅ Implemented | `OrderProductLink.price/cost` |
| **Kanban View** | Drag & Drop UI | ✅ Implemented | `admin/kanban.py` |
| **Documents** | PDF (Quote, Invoice, Work Order) | ✅ Implemented (Google API) | `document_service.py` |
| **Inventory Alert** | Warn if stock < 3 at Proposal | ✅ Implemented | `OrderAdmin.on_model_change` |
| **Dashboard** | Funnel, Action Items, Load | ✅ Backend Ready | `analytics_service.py` |
| **Stalled Logic** | Auto-defer after 14 days | ❌ **Missing** | Scheduler only does price sync |
| **Installer Bot** | Notify installer on assignment | ❌ **Missing** | Bot exists, but no trigger logic |
| **Soft Booking** | Calendar "Draft" events | ⚠️ Partial | Calendar logic not fully visible in Admin |

## 4. Recommendations & Updates

### Strategic
1.  **Prioritize the "Stalled Deal" Supervisor:** A robust CRM shouldn't just store data; it should drive action. Implementing a background job to flag stagnant deals is high priority.
2.  **Close the Loop with Installers:** Connect the `OrderInstaller` assignment in Admin to the `bot_app`. When a manager assigns "John Doe" to "Order #123", John should get a TG message with the address and "Work Order" link.

### Technical
1.  **Scheduler Update:** Expand `scheduler_service.py` to include a `check_stalled_deals()` method running daily.
2.  **Webhooks/Signals:** Use SQLAlchemy events or Service layer hooks to trigger Telegram messages on status changes.

## 5. Proposed Roadmap (New Phases)

Based on the analysis, here are the suggested next steps:

### Phase 6: Operational Dashboard & Analytics (Current)
*Goal: Visualize the business pulse.*
- [ ] **Fix Dashboard UI:** Resolve `undefined` widget and "Loading..." infinite loop (JS/API mismatch).
- [ ] Connect `analytics_service.py` to the frontend template correctly.
- [ ] Add "Overdue Assessments" alerts to the dashboard.

### Phase 7: Automation & Notifications (New)
*Goal: Reduce manual management overhead.*
- [ ] **Stalled Deal Supervisor:** Auto-move deals to `DEFERRED` if inactive > 14 days.
- [ ] **Installer Bot Integration:** Send "New Job" notifications via Telegram.
- [ ] **Status Alerts:** Notify managers if "Action Items" are overdue.

### Phase 8: Resource Calendar (New)
*Goal: Visual scheduling.*
- [ ] Implement a Calendar View in SQLAdmin (using FullCalendar.js).
- [ ] Visualize "Soft Bookings" (Negotiation) vs "Hard Bookings" (Installation).
