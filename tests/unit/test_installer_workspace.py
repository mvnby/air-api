"""Real HTTP projections, collection concurrency tokens and private material ACL."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select

from core.database import get_session
from core.config import settings
from core.security import create_access_token
from models import (
    Customer,
    CustomerEquipment,
    Order,
    OrderAttachmentLink,
    OrderProductLink,
    OrderProposal,
    OrderServiceLink,
    OrderWorkAssignment,
    OrderWorkStage,
    Payment,
    Product,
    ServiceAttachment,
    StaffUser,
    TenantWorkerProfile,
)
from routers.installer_workspace import router as installer_router
from routers.manager_installer_workspace import router as manager_router
from services.installer_collection_service import InstallerWorkspaceError
from services.installer_material_service import InstallerMaterialService as Materials
from services.installer_workspace_service import InstallerWorkspaceService as Workspace
from tests.unit.test_manager_multicompany import multi_db as multi_db
from tests.unit.test_order_responsibility import (
    responsibility_db as responsibility_db,
    headers,
)
from tests.unit.test_worker_assignments import worker


def installer_headers(staff_id=22, *, tenant=1, site="main"):
    return {
        "Authorization": "Bearer "
        + create_access_token(
            {
                "sub": "installer" if staff_id == 22 else "candidate",
                "staff_user_id": staff_id,
                "auth_version": 1,
            }
        ),
        "X-MVN-Manager-Tenant": str(tenant),
        "X-MVN-Manager-Storefront": site,
    }


@pytest.fixture
async def workspace_db(responsibility_db):  # noqa: F811 - imported shared fixture
    session = responsibility_db
    user = await session.get(StaffUser, 22)
    user.roles, user.primary_role = ["installer"], "installer"
    session.add(
        Customer(
            id=1, tenant_id=1, name="Клиент", phone="+375290000000", iban="PRIVATE-BANK"
        )
    )
    session.add(
        Product(
            id=1,
            title="Техническая модель",
            slug="unit",
            price=9999,
            specs={
                "refrigerant": "R32",
                "supplier": "PRIVATE-SUPPLIER",
                "cost": "PRIVATE-COST",
            },
        )
    )
    await session.flush()
    order = await session.get(Order, 100)
    order.customer_id, order.delivery_address = 1, "Адрес монтажа"
    order.comment, order.title = "PRIVATE-COST", "PRIVATE-SUPPLIER"
    order.total_amount, order.total_cost, order.margin = 77777, 44444, 33333
    order.target_currency, order.target_currency_amount = "EUR", 500
    session.add_all(
        [
            OrderProductLink(
                id=1,
                order_id=100,
                product_id=1,
                title_snapshot="Оборудование",
                price=1000,
                cost=777,
            ),
            OrderServiceLink(
                id=1,
                order_id=100,
                title="Монтаж",
                price=Decimal("50.25"),
                cost=Decimal("39.99"),
            ),
            CustomerEquipment(
                id=1,
                customer_id=1,
                source_order_id=100,
                brand="Brand",
                model="Model",
                serial="SERIAL",
                refrigerant_type="R32",
                notes="PRIVATE-COST",
            ),
            CustomerEquipment(id=2, customer_id=1, display_name="UNRELATED-EQUIPMENT"),
        ]
    )
    for identifier, category, kind, mime in [
        (1, "nameplate", "image", "image/jpeg"),
        (2, "document", "pdf", "application/pdf"),
        (3, "installation_result", "pdf", "application/pdf"),
    ]:
        session.add(
            ServiceAttachment(
                id=identifier,
                original_filename="PRIVATE-SUPPLIER.pdf",
                file_kind=kind,
                mime_type=mime,
                storage_key=f"private/{identifier}",
                transcript="PRIVATE-COST",
            )
        )
        await session.flush()
        session.add(
            OrderAttachmentLink(
                id=identifier,
                order_id=100,
                attachment_id=identifier,
                category=category,
                caption="PRIVATE-COST",
            )
        )
    await session.commit()
    app = FastAPI()
    app.include_router(installer_router)
    app.include_router(manager_router)
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield session, client


async def assign(client, staff_id=22, **kwargs):
    result = await client.post(
        "/api/manager/orders/100/installer-workspace/assignments",
        headers=headers(),
        json={"staff_user_id": staff_id, **kwargs},
    )
    assert result.status_code == 201, result.text
    return result.json()


def instruction(workspace, amount="10.25", *, currency="BYN", assignment_id=None):
    return {
        "expected_version": workspace["collection"]["version"],
        "assignment_id": assignment_id or workspace["assignments"][0]["id"],
        "amount": amount,
        "currency": currency,
        "financial_fingerprint": workspace["financial_fingerprint"],
    }


async def test_http_scope_read_only_minimal_equipment_and_no_repair(
    workspace_db, monkeypatch
):
    session, client = workspace_db
    assert (
        await client.get("/api/installer/works", headers=installer_headers())
    ).json()["total"] == 0
    data = await assign(client)
    assignment_id = data["assignments"][0]["id"]
    statements = []

    def inspect(state):
        statements.append(state.statement)

    event.listen(session.sync_session, "do_orm_execute", inspect)
    monkeypatch.setattr(
        Order,
        "calculate_totals",
        lambda *args: pytest.fail("Installer read recalculated CRM finances"),
    )
    try:
        response = await client.get(
            f"/api/installer/works/{assignment_id}", headers=installer_headers()
        )
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        detail = response.json()
        assert (
            detail["title"] == "Монтаж"
            and detail["instructions"] == ""
            and detail["materials"] == []
        )
        assert (
            detail["customer_phone"] == "+375290000000"
            and detail["address"] == "Адрес монтажа"
        )
        assert [item["key"] for item in detail["equipment"]] == [
            "equipment:1",
            "product:1",
        ]
        assert "PRIVATE" not in response.text and "UNRELATED" not in response.text
        for field in (
            "price",
            "cost",
            "margin",
            "payments",
            "suppliers",
            "comment",
            "financial_fingerprint",
        ):
            assert f'"{field}"' not in response.text
        assert (
            await client.get(
                "/api/installer/works?limit=101", headers=installer_headers()
            )
        ).status_code == 422
        assert (
            await client.get(
                "/api/manager/orders/100/installer-workspace",
                headers=installer_headers(),
            )
        ).status_code == 403
        assert (
            await client.post(
                f"/api/installer/works/{assignment_id}",
                headers=installer_headers(),
                json={},
            )
        ).status_code == 405
        assert (
            await client.get(
                f"/api/installer/works/{assignment_id}",
                headers=installer_headers(site="second"),
            )
        ).status_code == 404
        assert (
            await client.get(
                f"/api/installer/works/{assignment_id + 999}",
                headers=installer_headers(),
            )
        ).status_code == 404
    finally:
        event.remove(session.sync_session, "do_orm_execute", inspect)
    assert all(
        getattr(statement, "_for_update_arg", None) is None
        and not getattr(statement, "is_dml", False)
        for statement in statements
    )
    order = await session.get(Order, 100)
    assert (order.total_amount, order.total_cost, order.margin) == (77777, 44444, 33333)
    assert await session.scalar(select(OrderProposal.id)) is None


async def test_collection_zero_recipient_live_payments_and_stale_conflict(workspace_db):
    session, client = workspace_db
    data = await assign(client)
    identifier = data["assignments"][0]["id"]
    path = "/api/manager/orders/100/installer-workspace/collection"
    assert (
        await client.get(
            f"/api/installer/works/{identifier}", headers=installer_headers()
        )
    ).json()["collection"]["status"] == "not_assigned"
    saved = await client.put(
        path, headers=headers(), json=instruction(data, "0.00", currency="EUR")
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["collection"]["amount"] == "0.00"
    assert (
        await client.get(
            f"/api/installer/works/{identifier}", headers=installer_headers()
        )
    ).json()["collection"]["status"] == "ready"
    assert (
        await client.put(path, headers=headers(), json=instruction(data))
    ).status_code == 409
    data = saved.json()
    saved = await client.put(path, headers=headers(), json=instruction(data, "100.25"))
    assert saved.status_code == 200, saved.text
    other = await assign(client, 20)
    second = next(a["id"] for a in other["assignments"] if a["staff_user_id"] == 20)
    view = await Workspace.detail(session, worker(20), second)
    assert (
        view.collection.status == "not_collector"
        and view.collection.amount is None
        and view.collection.currency is None
    )
    assert view.collection.recipient_name == "Installer"
    session.add(Payment(order_id=100, amount=10, currency="BYN", comment="PRIVATE"))
    await session.commit()
    current = await client.get(
        f"/api/installer/works/{identifier}", headers=installer_headers()
    )
    assert (
        current.json()["collection"]["status"] == "requires_review"
        and current.json()["collection"]["amount"] is None
    )
    assert (
        await client.put(
            path, headers=headers(), json=instruction(saved.json(), "20.00")
        )
    ).status_code == 409
    refreshed = (
        await client.get(
            "/api/manager/orders/100/installer-workspace", headers=headers()
        )
    ).json()
    confirmed = await client.put(
        path, headers=headers(), json=instruction(refreshed, "20.00")
    )
    assert (
        confirmed.status_code == 200
        and confirmed.json()["collection"]["status"] == "ready"
    )
    assert len(list((await session.scalars(select(Payment))).all())) == 1
    cleared = await client.put(
        path,
        headers=headers(),
        json={
            "expected_version": confirmed.json()["collection"]["version"],
            "assignment_id": None,
            "financial_fingerprint": confirmed.json()["financial_fingerprint"],
        },
    )
    assert (
        cleared.status_code == 200
        and cleared.json()["collection"]["status"] == "not_assigned"
    )


@pytest.mark.parametrize(
    "amount,currency,status",
    [
        ("1050.26", "BYN", 400),
        ("500.01", "EUR", 400),
        ("1", "USD", 400),
        ("-1", "BYN", 422),
        ("0.001", "BYN", 422),
        ("NaN", "BYN", 422),
        (None, "BYN", 422),
    ],
)
async def test_collection_exact_money_and_current_balance(
    workspace_db, amount, currency, status
):
    _, client = workspace_db
    data = await assign(client)
    result = await client.put(
        "/api/manager/orders/100/installer-workspace/collection",
        headers=headers(),
        json=instruction(data, amount, currency=currency),
    )
    assert result.status_code == status, result.text


async def test_ambiguous_proposals_or_unconvertible_payment_fail_closed(workspace_db):
    session, client = workspace_db
    data = await assign(client)
    session.add(Payment(order_id=100, amount=10, currency="USD"))
    await session.commit()
    data = (
        await client.get(
            "/api/manager/orders/100/installer-workspace", headers=headers()
        )
    ).json()
    assert data["balances"] == []
    assert (
        await client.put(
            "/api/manager/orders/100/installer-workspace/collection",
            headers=headers(),
            json=instruction(data),
        )
    ).status_code == 400
    for payment in (await session.scalars(select(Payment))).all():
        await session.delete(payment)
    session.add_all(
        [
            OrderProposal(order_id=100, title="Variant one", is_selected=False),
            OrderProposal(order_id=100, title="Variant two", is_selected=False),
        ]
    )
    await session.commit()
    assert (
        await client.get(
            "/api/manager/orders/100/installer-workspace", headers=headers()
        )
    ).json()["balances"] == []


async def publish(client, data, links):
    row = data["assignments"][0]
    return await client.patch(
        f"/api/manager/orders/100/installer-workspace/assignments/{row['id']}",
        headers=headers(),
        json={
            "expected_version": row["version"],
            "title": "Установка",
            "instructions": "Согласованный вход во двор",
            "material_link_ids": links,
        },
    )


async def test_materials_explicit_allowlist_no_metadata_and_http_no_cache(
    workspace_db, monkeypatch
):
    session, client = workspace_db
    data = await assign(client)
    identifier = data["assignments"][0]["id"]
    assert (await publish(client, data, [2])).status_code == 400
    saved = await publish(client, data, [1, 3])
    assert saved.status_code == 200, saved.text
    detail = await client.get(
        f"/api/installer/works/{identifier}", headers=installer_headers()
    )
    assert detail.status_code == 200 and len(detail.json()["materials"]) == 2
    assert "PRIVATE" not in detail.text
    storage = AsyncMock()
    storage.read.return_value = b"test-image"
    monkeypatch.setattr(
        "services.installer_material_service.get_private_attachment_storage",
        lambda *args: storage,
    )
    url = detail.json()["materials"][0]["content_url"]
    content = await client.get(
        url, headers={**installer_headers(), "If-None-Match": '"any"'}
    )
    assert content.status_code == 200 and content.content == b"test-image"
    assert (
        content.headers["cache-control"] == "private, no-store"
        and "PRIVATE" not in content.headers["content-disposition"]
    )
    row = saved.json()["assignments"][0]
    revoke = await client.post(
        f"/api/manager/orders/100/installer-workspace/assignments/{identifier}/revoke",
        headers=headers(),
        json={"expected_version": row["version"]},
    )
    assert revoke.status_code == 200
    assert (
        await client.get(url, headers={**installer_headers(), "If-None-Match": '"any"'})
    ).status_code == 404
    assert (
        await client.get(
            f"/api/installer/works/{identifier}", headers=installer_headers()
        )
    ).status_code == 404


@pytest.mark.parametrize(
    "change",
    ["assignment", "profile", "member", "file", "publication", "stage", "auth_version"],
)
async def test_material_rechecks_authorization_after_storage_io(workspace_db, change):
    from models import TenantMembership
    from models.installer_publication import InstallerMaterialPublication

    session, client = workspace_db
    session.add(OrderWorkStage(id=10, order_id=100, name="PRIVATE"))
    await session.commit()
    data = await assign(client, work_stage_id=10)
    saved = await publish(client, data, [1])
    assert saved.status_code == 200, saved.text
    identifier = data["assignments"][0]["id"]
    publication = await session.scalar(select(InstallerMaterialPublication))

    async def read(key):
        assignment = await session.get(OrderWorkAssignment, identifier)
        if change == "assignment":
            assignment.revoked_at = datetime.now()
        elif change == "profile":
            (
                await session.get(TenantWorkerProfile, assignment.worker_profile_id)
            ).status = "disabled"
        elif change == "member":
            member = await session.scalar(
                select(TenantMembership).where(TenantMembership.staff_user_id == 22)
            )
            member.status = "disabled"
        elif change == "file":
            (await session.get(ServiceAttachment, 1)).archived_at = datetime.now()
        elif change == "publication":
            publication.revoked_at = datetime.now()
        elif change == "auth_version":
            (await session.get(StaffUser, 22)).auth_version += 1
        else:
            (await session.get(OrderWorkStage, 10)).status = "canceled"
        await session.commit()
        return b"sensitive-bytes"

    with pytest.raises((InstallerWorkspaceError, ValueError)):
        await Materials.read_content(
            session,
            auth=worker(),
            assignment_id=identifier,
            material_id=publication.id,
            storage=type("Storage", (), {"read": staticmethod(read)})(),
        )


async def test_manager_atomic_projection_failure_and_team_protection(
    workspace_db, monkeypatch
):
    session, client = workspace_db
    path = "/api/manager/orders/100/installer-workspace/assignments"
    assert (
        await client.post(path, headers=headers(team=False), json={"staff_user_id": 22})
    ).status_code == 403
    assert (
        await client.post(
            path,
            headers={**headers(), "Origin": "https://foreign.invalid"},
            json={"staff_user_id": 22},
        )
    ).status_code == 403
    original = Workspace.manager_view
    monkeypatch.setattr(
        Workspace,
        "manager_view",
        AsyncMock(side_effect=RuntimeError("projection failed")),
    )
    with pytest.raises(RuntimeError, match="projection failed"):
        await client.post(path, headers=headers(), json={"staff_user_id": 22})
    assert await session.scalar(select(OrderWorkAssignment.id)) is None
    monkeypatch.setattr(Workspace, "manager_view", original)
    commit = AsyncMock(wraps=session.commit)
    monkeypatch.setattr(session, "commit", commit)
    await assign(client)
    assert commit.await_count == 1


async def test_date_bucket_count_before_pagination_and_null_dates(workspace_db):
    session, client = workspace_db
    now = datetime.now(ZoneInfo(settings.BOT_TASK_TIMEZONE)).replace(tzinfo=None)
    for identifier, start in [(10, now), (11, now + timedelta(days=2)), (12, None)]:
        session.add(
            OrderWorkStage(
                id=identifier, order_id=100, name="PRIVATE", start_time=start
            )
        )
    await session.commit()
    for identifier in (10, 11, 12):
        await assign(client, work_stage_id=identifier)
    for bucket in ("today", "upcoming", "unscheduled"):
        response = await client.get(
            f"/api/installer/works?bucket={bucket}&page=1&limit=1",
            headers=installer_headers(),
        )
        assert (
            response.status_code == 200
            and response.json()["total"] == 1
            and len(response.json()["items"]) == 1
        )
    assert (
        await client.get(
            "/api/installer/works?bucket=all&limit=1", headers=installer_headers()
        )
    ).json()["total"] == 3
