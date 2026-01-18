---
description: Custom workflow for CRM Feature Development using Analysis, Browser Verification, and Gap Logic.
---

# CRM Feature Development Workflow

Follow this standardized process for implementing new features or analyzing existing ones in the CRM project.

## 1. Analysis & Design Review
- [ ] Read the architectural documentation (`docs/CRM...Analysis...md`).
- [ ] Review relevant codebase files (`models.py`, `services/`, `admin/`).
- [ ] Create or Update `docs/Gap_Analysis_Report.md` if investigating an existing implementation.
- [ ] **Goal:** Understand the "Ideal State" vs "Current State".

## 2. Browser-Based Verification (UI/UX)
// turbo
- [ ] Launch the application: `./manage.sh start`.
- [ ] Use `browser_subagent` to visually inspect the feature.
    - Login if needed (minad/kr0tik).
    - Navigate to relevant Admin pages.
    - Capture screenshots of key UI elements.
    - **Crucial:** Verify data loading, widget visibility, and user flows (e.g., Drag & Drop).
- [ ] Stop the application: `./manage.sh stop`.

## 3. Planning & Documentation
- [ ] Create/Update `task.md` with a detailed checklist.
- [ ] Create `implementation_plan.md` outlining specific code changes.
    - Must include **Goal**, **User Review Required**, **Proposed Changes**, and **Verification Plan**.
- [ ] Request User Review via `notify_user`.

## 4. Execution (Code & Fix)
- [ ] Create a new branch: `git checkout -b feature/phase-NAME`.
- [ ] Implement backend logic (`services/`).
- [ ] Implement UI changes (`templates/`, `admin/`).
- [ ] Ensure strict separation of concerns (Service Layer pattern).

## 5. Verification & Delivery
- [ ] Restart app and verify fixes via Browser (Screenshots).
- [ ] Create `walkthrough.md` with "Before/After" or "Result" screenshots.
- [ ] Commit changes: `git commit -m "feat: ..."`
- [ ] Update `docs/AI_AGENT_CONTEXT.md` with the new feature status.
