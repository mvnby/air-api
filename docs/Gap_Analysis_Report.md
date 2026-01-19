# CRM Gap Analysis & Progress Report

**Date:** 2026-01-19  
**Based on:** `CRM для кондиционеров_ Анализ и Проектирование.md` & Codebase Review

## 1. Executive Summary
The CRM implementation has advanced significantly. **Phase 7 (Automation)** and **Phase 8 (Resource Calendar)** are effectively **Complete**. The backend logic for stalled deals and installer notifications is in place. The Calendar view is functional.
However, a **Critical Regression** was found in **Phase 6 (Dashboard)**: The main admin dashboard widgets are broken (`undefined`) and tables are not loading. This requires immediate attention before adding new features.

## 2. Component Analysis

### ✅ Data Model (100% Complete)
The database schema (`models.py`) is a near-perfect match to the design:
- **Order Structure:** Implemented with `technical_meta` (JSON), `total_amount`, `margin`.
- **Snapshot Pricing:** `OrderProductLink` fixes `price` and `cost` at the moment of sale.
- **Installers:** `OrderInstaller` supports `agreed_pay` (job-specific rates) and `role`.
- **Statuses:** Full `OrderStatus` enum is implemented correctly.

### ✅ Admin Interface (90% Complete)
- **Kanban Board:** Backend logic (`admin/kanban.py`) and UI are fully functional.
- **Calendar (Phase 8):** `admin/calendar.py` and template are working. **UI Verification:** Month view renders correctly with events.
- **Order Management:** `OrderAdmin` includes status coloring and custom search/filtering.
- **Dashboard (Phase 6):** The backend service (`analytics_service.py`) calculates metrics.
    - ❌ **UI Issues:** Browser verification confirmed **CRITICAL BUGS**:
        - "Active on Site", "Orders", "Products" widgets show `undefined`.
        - "Latest Orders" table is stuck on "Loading...".
        - "Latest Products" table is empty.

### ✅ Business Logic & Automation (95% Complete)
- **Document Generation:** Implemented via `document_service.py` (Google Docs).
- **Inventory Reservation:** Implemented via `OrderStatus` logic.
- **Stalled Deal Automation (Phase 7):** `scheduler_service.py` contains `check_stalled_deals` logic (Auto-defer > 14 days).
- **Installer Notifications (Phase 7):** `BotService.notify_installer_new_order` is hooked into `OrderService.update_order_installers`. Notifications are sent when installers are assigned.

## 3. Gap Analysis Table

| Feature | Design Requirement | Current Status | Validation |
| :--- | :--- | :--- | :--- |
| **Pipeline Stages** | 7 Distinct Stages | ✅ Implemented | `OrderStatus` enum |
| **Snapshot Pricing** | Store cost/price at sale | ✅ Implemented | `OrderProductLink.price/cost` |
| **Kanban View** | Drag & Drop UI | ✅ Implemented | `admin/kanban.py` |
| **Documents** | PDF (Quote, Invoice, Work Order) | ✅ Implemented (Google API) | `document_service.py` |
| **Inventory Alert** | Warn if stock < 3 at Proposal | ✅ Implemented | `OrderAdmin.on_model_change` |
| **Dashboard** | Funnel, Action Items, Load | ❌ **Broken UI** | Backend ready, Frontend fails |
| **Stalled Logic** | Auto-defer after 14 days | ✅ Implemented | `scheduler_service.py` |
| **Installer Bot** | Notify installer on assignment | ✅ Implemented | `OrderService` -> `BotService` |
| **Soft Booking** | Calendar "Draft" events | ✅ Implemented | `admin/calendar.py` events |

## 4. Recommendations & Updates

### Strategic
1.  **Prioritize the "Stalled Deal" Supervisor:** A robust CRM shouldn't just store data; it should drive action. Implementing a background job to flag stagnant deals is high priority.
2.  **Close the Loop with Installers:** Connect the `OrderInstaller` assignment in Admin to the `bot_app`. When a manager assigns "John Doe" to "Order #123", John should get a TG message with the address and "Work Order" link.

### Technical
1.  **Scheduler Update:** Expand `scheduler_service.py` to include a `check_stalled_deals()` method running daily.
2.  **Webhooks/Signals:** Use SQLAlchemy events or Service layer hooks to trigger Telegram messages on status changes.

## 5. Proposed Roadmap (New Phases)

### Phase 9: Dashboard Stabilization (Priority)
*Goal: Restore system observability.*
- [ ] **Fix Dashboard Widgets:** Debug JS/API mismatch for `active`, `orders_count`, `products_count`.
- [ ] **Fix Data Tables:** Resolve "Loading..." state for Orders and empty Products table.
- [ ] **Verify Analytics:** Ensure numbers from `analytics_service.py` match the database reality.

### Phase 10: Advanced Reporting (Future)
*Goal: Deep financial insights.*
- [ ] Sales Funnel visualization (Chart.js integration).
- [ ] Installer/Crew Load verification.
