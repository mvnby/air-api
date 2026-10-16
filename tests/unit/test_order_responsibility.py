"""Real HTTP identities, SQLite transactions and minimal responsibility projections."""

from dataclasses import replace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from api_contracts.order_responsibility import ManagerOrderResponsibleUpdate
from core.config import settings
from core.database import get_session
from core.security import AuthenticatedUser, create_access_token
from models import Order, StaffUser, Storefront, Tenant, TenantAuditEvent, TenantMembership
from models.tenancy import TenantScope
from routers.manager_order_responsibility import router
from services.order_responsibility_service import OrderResponsibilityService as Service, OrderResponsibilityError
from tests.unit.test_manager_multicompany import multi_db


@pytest.fixture
async def responsibility_db(multi_db):
    session = multi_db
    session.add_all([
        StaffUser(id=20, display_name="Candidate", username="candidate", avatar_version="a" * 64),
        StaffUser(id=21, display_name="Inactive", username="inactive", status="inactive"),
        StaffUser(id=22, display_name="Installer", username="installer"),
        StaffUser(id=23, display_name="Editor", username="editor"),
        StaffUser(id=24, display_name="Alias", username="alias", merged_into_staff_user_id=20),
        StaffUser(id=25, display_name="Partner", username="partner"),
        StaffUser(id=26, display_name="Disabled member", username="disabled-member"),
    ])
    await session.flush()
    session.add_all([
        TenantMembership(tenant_id=1, staff_user_id=20, role="manager"),
        TenantMembership(tenant_id=1, staff_user_id=21, role="manager"),
        TenantMembership(tenant_id=1, staff_user_id=22, role="installer"),
        TenantMembership(tenant_id=1, staff_user_id=23, role="catalog_editor"),
        TenantMembership(tenant_id=1, staff_user_id=24, role="owner"),
        TenantMembership(tenant_id=2, staff_user_id=25, role="manager"),
        TenantMembership(tenant_id=1, staff_user_id=26, role="manager", status="disabled"),
        Storefront(id=4, tenant_id=1, slug="second", display_name="Second", status="active"),
        Order(id=100, tenant_id=1, storefront_id=1, user_id=999),
        Order(id=200, tenant_id=2, storefront_id=2),
        Order(id=300, tenant_id=3, storefront_id=3),
        Order(id=400, tenant_id=1, storefront_id=4),
    ])
    await session.commit()
    yield session


def auth(staff_id=10, tenant_id=1, **kwargs):
    return AuthenticatedUser(username="person" if staff_id == 10 else settings.ADMIN_USERNAME,
        auth_source="staff_password", staff_user_id=staff_id, auth_version=1,
        role="manager", tenant_id=tenant_id, storefront_id=tenant_id, **kwargs)


def headers(staff_id=10, tenant_id=1, *, team=True):
    username = "person" if staff_id == 10 else settings.ADMIN_USERNAME
    result = {"Authorization": "Bearer " + create_access_token({"sub": username, "staff_user_id": staff_id, "auth_version": 1}),
              "X-MVN-Manager-Tenant": str(tenant_id), "Origin": "http://test"}
    if team:
        result["X-Kitlane-Team"] = "1"
    return result


def app_for(session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    return app


async def test_candidate_http_is_read_only_minimal_actual_and_paginated(responsibility_db):
    session = responsibility_db
    seen = []
    def inspect(execution):
        seen.append(execution.statement)
    event.listen(session.sync_session, "do_orm_execute", inspect)
    try:
        async with AsyncClient(transport=ASGITransport(app=app_for(session)), base_url="http://test") as client:
            response = await client.get("/api/manager/order-responsibles", headers=headers())
            assert response.status_code == 200, response.text
            data = response.json()
            assert {item["staff_user_id"] for item in data["items"]} == {4, 10, 20}
            assert data["total"] == 3
            assert all(set(item) == {"staff_user_id", "display_name", "avatar_url", "is_active"} for item in data["items"])
            assert all(item["is_active"] for item in data["items"])
            assert next(item for item in data["items"] if item["staff_user_id"] == 20)["avatar_url"].startswith("/api/manager/staff/20/avatar?tenant_id=1&v=")
            page = await client.get("/api/manager/order-responsibles?page=2&limit=1", headers=headers())
            assert page.status_code == 200 and len(page.json()["items"]) == 1
            assert (await client.get("/api/manager/order-responsibles?limit=101", headers=headers())).status_code == 422
            assert (await client.get("/api/manager/order-responsibles", headers=headers(tenant_id=2))).status_code == 403
            support = await client.get("/api/manager/order-responsibles", headers=headers(4, 2))
            assert support.status_code == 200 and [item["staff_user_id"] for item in support.json()["items"]] == [25]
    finally:
        event.remove(session.sync_session, "do_orm_execute", inspect)
    assert all(getattr(stmt, "_for_update_arg", None) is None and not getattr(stmt, "is_dml", False) for stmt in seen)


async def test_http_assign_clear_stale_and_noop_are_audited_atomically(responsibility_db):
    session = responsibility_db
    async with AsyncClient(transport=ASGITransport(app=app_for(session)), base_url="http://test") as client:
        path = "/api/manager/orders/100/responsible"
        payload = {"responsible_staff_user_id": 20, "expected_version": 0}
        assert (await client.patch(path, headers=headers(team=False), json=payload)).status_code == 403
        assert (await client.patch(path, headers={**headers(), "Origin": "https://foreign.invalid"}, json=payload)).status_code == 403
        changed = await client.patch(path, headers=headers(), json=payload)
        assert changed.status_code == 200, changed.text
        assert changed.json()["responsible_version"] == 1
        assert changed.json()["responsible_person"]["staff_user_id"] == 20
        assert (await session.get(Order, 100)).user_id == 999
        assert (await client.patch(path, headers=headers(), json=payload)).status_code == 409
        same = await client.patch(path, headers=headers(), json={**payload, "expected_version": 1})
        assert same.status_code == 200 and same.json()["responsible_version"] == 1
        cleared = await client.patch(path, headers=headers(), json={"responsible_staff_user_id": None, "expected_version": 1})
        assert cleared.status_code == 200 and cleared.json()["responsible_version"] == 2 and cleared.json()["responsible_person"] is None
    audits = list((await session.scalars(select(TenantAuditEvent).where(TenantAuditEvent.action == "order.responsible_changed"))).all())
    assert len(audits) == 2
    assert audits[0].actor_staff_user_id == 10 and audits[0].tenant_id == 1 and audits[0].entity_id == 100
    assert audits[0].change_set == {"responsible_staff_user_id": {"before": None, "after": 20}, "responsible_version": {"before": 0, "after": 1}}


@pytest.mark.parametrize("candidate", [21, 22, 23, 24, 25, 26, 999])
async def test_new_assignment_rejects_ineligible_or_foreign_member(responsibility_db, candidate):
    session = responsibility_db
    with pytest.raises(OrderResponsibilityError) as caught:
        await Service.assign(session, order_id=100, payload=ManagerOrderResponsibleUpdate(responsible_staff_user_id=candidate, expected_version=0), auth=auth())
    assert caught.value.code == "responsible_unavailable"
    await session.rollback()
    assert (await session.get(Order, 100)).responsible_version == 0
    assert not list((await session.scalars(select(TenantAuditEvent))).all())


async def test_historical_projection_retains_inactive_demoted_and_alias_people(responsibility_db):
    session = responsibility_db
    order = await session.get(Order, 100)
    for staff_id in (21, 23, 24, 26):
        order.responsible_staff_user_id = staff_id
        await session.commit()
        mapped = await Service.person_map(session, [order])
        assert mapped[100].staff_user_id == staff_id and not mapped[100].is_active
    # Keeping the existing inactive assignee is a no-op, not a new assignment.
    detail = await Service.assign(session, order_id=100, payload=ManagerOrderResponsibleUpdate(responsible_staff_user_id=26, expected_version=0), auth=auth())
    assert detail["responsible_version"] == 0
    assert not list((await session.scalars(select(TenantAuditEvent))).all())


async def test_support_actual_candidates_scope_and_live_actor_fences(responsibility_db):
    session = responsibility_db
    payload = ManagerOrderResponsibleUpdate(responsible_staff_user_id=25, expected_version=0)
    support = auth(4, 2, access_kind="platform_support", is_platform_owner=True)
    assigned = await Service.assign(session, order_id=200, payload=payload, auth=support)
    assert assigned["responsible_person"].staff_user_id == 25
    with pytest.raises(OrderResponsibilityError) as denied:
        await Service.assign(session, order_id=200, payload=ManagerOrderResponsibleUpdate(responsible_staff_user_id=4, expected_version=1), auth=support)
    assert denied.value.code == "responsible_unavailable"
    await session.rollback()
    for order_id in (200, 400):
        with pytest.raises(OrderResponsibilityError) as foreign:
            await Service.assign(session, order_id=order_id, payload=payload, auth=auth())
        assert foreign.value.status_code == 404
        await session.rollback()
    with pytest.raises(OrderResponsibilityError) as emergency:
        await Service.assign(session, order_id=100, payload=payload, auth=replace(auth(), staff_user_id=None))
    assert emergency.value.code == "staff_account_required"
    for changed_auth in (replace(auth(), auth_version=0), auth(4, 3, access_kind="platform_support", is_platform_owner=True)):
        with pytest.raises(OrderResponsibilityError) as denied:
            await Service.assign(session, order_id=100, payload=payload, auth=changed_auth)
        assert denied.value.status_code == 403
        await session.rollback()
    actor_membership = await session.get(TenantMembership, 10)
    actor_membership.role = "catalog_editor"
    await session.commit()
    with pytest.raises(OrderResponsibilityError) as revoked:
        await Service.assign(session, order_id=100, payload=payload, auth=auth())
    assert revoked.value.code == "responsible_access_denied"


async def test_initial_allocation_never_creates_virtual_memberships_or_rewrites_history(responsibility_db):
    session = responsibility_db
    assert await Service.initial_responsible(session, TenantScope(tenant_id=1, storefront_id=1), 10) == 10
    assert await Service.initial_responsible(session, TenantScope(tenant_id=2, storefront_id=2), 4) is None
    assert await Service.initial_responsible(session, TenantScope(tenant_id=1, storefront_id=1), 22) is None
    assert await Service.initial_responsible(session, TenantScope(tenant_id=1, storefront_id=1), None) is None
    assert (await session.get(Order, 100)).responsible_staff_user_id is None
    assert (await session.get(Order, 100)).responsible_version == 0


async def test_database_constraints_reject_foreign_assignee_and_negative_version(responsibility_db):
    session = responsibility_db
    await session.commit()
    await session.execute(text("PRAGMA foreign_keys=ON"))
    await session.commit()
    assert await session.scalar(text("PRAGMA foreign_keys")) == 1
    for values in ({"responsible_staff_user_id": 25}, {"responsible_version": -1}):
        order = await session.get(Order, 100)
        for key, value in values.items():
            setattr(order, key, value)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_failed_audit_rolls_back_assignment_and_counter(responsibility_db):
    session = responsibility_db
    def reject_audit(sync_session, *args):
        if any(isinstance(row, TenantAuditEvent) and row.action == "order.responsible_changed" for row in sync_session.new):
            raise RuntimeError("injected audit failure")
    event.listen(session.sync_session, "before_flush", reject_audit)
    try:
        with pytest.raises(RuntimeError, match="audit"):
            await Service.assign(session, order_id=100, payload=ManagerOrderResponsibleUpdate(responsible_staff_user_id=20, expected_version=0), auth=auth())
        await session.rollback()
    finally:
        event.remove(session.sync_session, "before_flush", reject_audit)
    order = await session.get(Order, 100)
    assert order.responsible_staff_user_id is None and order.responsible_version == 0
    assert not list((await session.scalars(select(TenantAuditEvent))).all())


async def test_assignment_owns_one_commit_without_repairing_legacy_proposals(responsibility_db, monkeypatch):
    from unittest.mock import AsyncMock
    from models import OrderProposal

    session = responsibility_db
    commit = AsyncMock(wraps=session.commit)
    monkeypatch.setattr(session, "commit", commit)
    await Service.assign(session, order_id=100,
        payload=ManagerOrderResponsibleUpdate(responsible_staff_user_id=20, expected_version=0), auth=auth())
    assert commit.await_count == 1
    assert not list((await session.scalars(select(OrderProposal).where(OrderProposal.order_id == 100))).all())


async def test_projection_failure_cannot_commit_assignment_before_owner_transaction(responsibility_db, monkeypatch):
    from services.order_projection_service import OrderProjectionService
    from models import OrderProposal

    session = responsibility_db
    project = OrderProjectionService.get_order_detail_for_manager
    async def fail_after_project(*args, **kwargs):
        await project(*args, **kwargs)
        raise RuntimeError("injected projection failure")
    monkeypatch.setattr(OrderProjectionService, "get_order_detail_for_manager", fail_after_project)
    with pytest.raises(RuntimeError, match="projection"):
        await Service.assign(session, order_id=100,
            payload=ManagerOrderResponsibleUpdate(responsible_staff_user_id=20, expected_version=0), auth=auth())
    await session.rollback()
    order = await session.get(Order, 100)
    assert order.responsible_staff_user_id is None and order.responsible_version == 0
    assert not list((await session.scalars(select(TenantAuditEvent))).all())
    assert not list((await session.scalars(select(OrderProposal).where(OrderProposal.order_id == 100))).all())


@pytest.mark.parametrize("no_change", [False, True])
async def test_assignment_preserves_unrelated_cached_money_and_order_fields(responsibility_db, no_change):
    session = responsibility_db
    order = await session.get(Order, 100)
    preserved = {
        "total_amount": 1234.0, "total_cost": 876.0, "margin": 358.0,
        "total_payments": 123.0, "balance_due": 1111.0, "target_currency_payments": 12.34,
        "title": "Existing order title", "comment": "Keep this comment", "user_id": 999,
        "technical_meta": {"imported": "keep-existing-metadata"},
    }
    for field, value in preserved.items():
        setattr(order, field, value)
    order.responsible_staff_user_id = 20 if no_change else None
    order.responsible_version = 4
    await session.commit()
    previous_updated_at = order.updated_at

    result = await Service.assign(session, order_id=100,
        payload=ManagerOrderResponsibleUpdate(responsible_staff_user_id=20, expected_version=4), auth=auth())
    assert result["responsible_person"].staff_user_id == 20
    assert result["responsible_version"] == (4 if no_change else 5)
    # Read scalar columns freshly from the DB, not the identity map. The order has
    # no lines/payments; an accidental calculate_totals would overwrite money with 0.
    stored = (await session.execute(select(*(getattr(Order, field) for field in preserved)).where(Order.id == 100))).one()
    assert dict(stored._mapping) == preserved
    if no_change:
        assert await session.scalar(select(Order.updated_at).where(Order.id == 100)) == previous_updated_at
    audits = list((await session.scalars(select(TenantAuditEvent).where(TenantAuditEvent.action == "order.responsible_changed"))).all())
    assert len(audits) == (0 if no_change else 1)
