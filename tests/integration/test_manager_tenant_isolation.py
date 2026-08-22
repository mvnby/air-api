from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import select

from core.security import create_access_token
from models import (
    AnalyticsConnection,
    Customer,
    CustomerEquipment,
    CustomerRequisitesRecognition,
    Installer,
    Lead,
    Order,
    OrderDocument,
    OrderStatus,
    OrderWorkStage,
    Payment,
    StaffUser,
    Storefront,
    Tenant,
    TenantMembership,
)
from models.common import CustomerType
from services.analytics_connection_service import AnalyticsCredentialCipher


async def _create_tenant(
    db,
    *,
    slug: str,
    is_system: bool = False,
) -> tuple[Tenant, Storefront]:
    tenant = Tenant(
        id=2,
        slug=slug,
        display_name=slug.upper(),
        kind="independent_seller",
        status="active",
        is_system=is_system,
    )
    db.add(tenant)
    await db.flush()
    storefront = Storefront(
        id=2,
        tenant_id=int(tenant.id),
        slug="main",
        display_name=f"{slug.upper()} Main",
        status="active",
        is_default=True,
    )
    db.add(storefront)
    await db.flush()
    return tenant, storefront


async def _create_staff(
    db,
    *,
    tenant_id: int | None,
    username: str,
    membership_role: str = "owner",
    membership_status: str = "active",
    global_role: str = "owner",
) -> StaffUser:
    user = StaffUser(
        display_name=username,
        status="active",
        primary_role=global_role,
        roles=[global_role],
        username=username,
    )
    db.add(user)
    await db.flush()
    if tenant_id is not None:
        db.add(
            TenantMembership(
                tenant_id=tenant_id,
                staff_user_id=int(user.id),
                role=membership_role,
                status=membership_status,
            )
        )
        await db.flush()
    return user


def _headers(user: StaffUser, *, claimed_role: str = "owner") -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "staff_user_id": user.id,
            "auth_version": user.auth_version,
            "role": claimed_role,
            "auth_source": "tenant-isolation-test",
        },
        expires_delta=timedelta(minutes=10),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_analytics_connections_require_owner_and_isolate_exact_scope(
    async_client: AsyncClient,
    db,
):
    unauthorized = await async_client.get("/api/manager/analytics-connections")
    assert unauthorized.status_code == 401

    tenant_b, storefront_b = await _create_tenant(db, slug="analytics-b")
    owner_a = await _create_staff(db, tenant_id=1, username="analytics-owner-a")
    manager_a = await _create_staff(
        db,
        tenant_id=1,
        username="analytics-manager-a",
        membership_role="manager",
        global_role="manager",
    )
    owner_b = await _create_staff(
        db,
        tenant_id=int(tenant_b.id),
        username="analytics-owner-b",
    )
    db.add_all(
        [
            AnalyticsConnection(
                tenant_id=1,
                storefront_id=1,
                provider="yandex_metrika",
                public_config={
                    "counter_id": "111",
                    "counter_name": "MVN",
                    "site": "mvn.by",
                },
                encrypted_credentials=AnalyticsCredentialCipher.encrypt(
                    {"oauth_token": "token-a-secret-value"}
                ),
                credentials_fingerprint="fingerprint-a",
            ),
            AnalyticsConnection(
                tenant_id=int(tenant_b.id),
                storefront_id=int(storefront_b.id),
                provider="yandex_metrika",
                public_config={
                    "counter_id": "222",
                    "counter_name": "Tenant B",
                    "site": "tenant-b.example",
                },
                encrypted_credentials=AnalyticsCredentialCipher.encrypt(
                    {"oauth_token": "token-b-secret-value"}
                ),
                credentials_fingerprint="fingerprint-b",
            ),
        ]
    )
    await db.commit()

    forbidden = await async_client.get(
        "/api/manager/analytics-connections",
        headers=_headers(manager_a, claimed_role="owner"),
    )
    owner_a_response = await async_client.get(
        "/api/manager/analytics-connections",
        params={"tenant_id": tenant_b.id, "storefront_id": storefront_b.id},
        headers=_headers(owner_a),
    )
    owner_b_response = await async_client.get(
        "/api/manager/analytics-connections",
        headers=_headers(owner_b),
    )

    assert forbidden.status_code == 403
    assert owner_a_response.status_code == 200
    assert owner_b_response.status_code == 200
    item_a = owner_a_response.json()["items"][0]
    item_b = owner_b_response.json()["items"][0]
    assert item_a["counter_id"] == "111"
    assert item_b["counter_id"] == "222"
    assert "token" not in str(owner_a_response.json()).lower()
    assert "token" not in str(owner_b_response.json()).lower()


@pytest.mark.asyncio
async def test_dashboard_overview_requires_auth_and_isolates_exact_storefront_scope(
    async_client: AsyncClient,
    db,
):
    unauthorized = await async_client.get("/api/manager/dashboard/overview")
    assert unauthorized.status_code == 401

    tenant_b, storefront_b = await _create_tenant(db, slug="overview-b")
    owner_a = await _create_staff(db, tenant_id=1, username="overview-owner-a")
    owner_b = await _create_staff(
        db,
        tenant_id=int(tenant_b.id),
        username="overview-owner-b",
    )
    now = datetime.now()
    lead_a = Lead(
        tenant_id=1,
        storefront_id=1,
        source="site",
        request_text="Scope A lead",
        next_followup_date=now + timedelta(days=60),
        created_at=now,
    )
    lead_b = Lead(
        tenant_id=int(tenant_b.id),
        storefront_id=int(storefront_b.id),
        source="site",
        request_text="Scope B lead",
        next_followup_date=now - timedelta(days=60),
        created_at=now,
    )
    sale_a = Order(
        tenant_id=1,
        storefront_id=1,
        status=OrderStatus.CLOSED,
        closing_result="won",
        closed_at=now,
        created_at=now - timedelta(days=2),
        updated_at=now,
    )
    sale_b = Order(
        tenant_id=int(tenant_b.id),
        storefront_id=int(storefront_b.id),
        status=OrderStatus.CLOSED,
        closing_result="won",
        closed_at=now,
        created_at=now - timedelta(days=3),
        updated_at=now,
    )
    receivable_a = Order(
        tenant_id=1,
        storefront_id=1,
        status=OrderStatus.NEGOTIATION,
        balance_due=250,
        created_at=now - timedelta(days=90),
    )
    receivable_b = Order(
        tenant_id=int(tenant_b.id),
        storefront_id=int(storefront_b.id),
        status=OrderStatus.EXECUTION,
        balance_due=900,
        created_at=now - timedelta(days=90),
    )
    db.add_all([lead_a, lead_b, sale_a, sale_b, receivable_a, receivable_b])
    await db.flush()
    db.add_all(
        [
            Payment(order_id=int(sale_a.id), amount=100, date=now),
            Payment(order_id=int(sale_b.id), amount=700, date=now),
            OrderWorkStage(
                order_id=int(sale_a.id),
                name="Монтаж",
                status="completed",
                end_time=now,
            ),
            OrderWorkStage(
                order_id=int(sale_b.id),
                name="Монтаж",
                status="completed",
                end_time=now,
            ),
            OrderWorkStage(
                order_id=int(sale_a.id),
                name="Закладка трассы",
                status="completed",
                end_time=now,
            ),
        ]
    )
    await db.commit()

    overview_a = await async_client.get(
        "/api/manager/dashboard/overview",
        params={"tenant_id": tenant_b.id, "storefront_id": storefront_b.id},
        headers=_headers(owner_a),
    )
    overview_b = await async_client.get(
        "/api/manager/dashboard/overview",
        headers=_headers(owner_b),
    )

    assert overview_a.status_code == 200
    assert overview_b.status_code == 200
    data_a = overview_a.json()
    data_b = overview_b.json()
    assert data_a["kpis"]["revenue"]["current"] == 100
    assert data_b["kpis"]["revenue"]["current"] == 700
    assert data_a["kpis"]["new_leads"]["current"] == 1
    assert data_b["kpis"]["new_leads"]["current"] == 1
    assert data_a["kpis"]["receivables"]["current"] == 250
    assert data_b["kpis"]["receivables"]["current"] == 900
    assert data_a["kpis"]["receivables"]["previous"] is None
    assert data_a["kpis"]["receivables"]["trend"] == "unavailable"
    assert data_a["kpis"]["active_tasks"]["previous"] is None
    assert data_a["kpis"]["active_tasks"]["trend"] == "unavailable"
    assert data_a["kpis"]["active_tasks"]["current"] == 1
    assert data_b["kpis"]["active_tasks"]["current"] == 1
    assert data_a["kpis"]["installations"]["current"] == 1
    assert data_b["kpis"]["installations"]["current"] == 1
    assert data_a["marketing"]["status"] == "unconfigured"
    assert [item["stage"] for item in data_a["funnel"]] == [
        "visitors",
        "leads",
        "measurements",
        "proposals",
        "sales",
        "installations",
    ]
    assert data_a["funnel"][0]["current"] is None
    today_a = next(
        item for item in data_a["sales_series"] if item["date"] == now.date().isoformat()
    )
    assert today_a == {"date": now.date().isoformat(), "revenue": 100, "sales": 1}


@pytest.mark.asyncio
async def test_customer_api_isolates_tenants(
    async_client: AsyncClient,
    db,
):
    tenant_b, storefront_b = await _create_tenant(db, slug="tenant-b")
    owner_a = await _create_staff(
        db,
        tenant_id=1,
        username="owner-a",
    )
    owner_b = await _create_staff(
        db,
        tenant_id=int(tenant_b.id),
        username="owner-b",
    )
    legacy = Customer(
        tenant_id=1,
        name="Legacy MVN",
        phone="+375290000001",
        type=CustomerType.individual,
    )
    customer_a = Customer(
        tenant_id=1,
        name="Tenant A",
        phone="+375290000002",
        type=CustomerType.individual,
    )
    customer_b = Customer(
        tenant_id=int(tenant_b.id),
        name="Tenant B",
        phone="+375290000003",
        type=CustomerType.individual,
    )
    recognition_b = CustomerRequisitesRecognition(
        tenant_id=int(tenant_b.id),
        source="manager",
        status="recognized",
        raw_text="ООО Tenant B УНП 123456789",
        extracted_json={
            "name": "ООО Tenant B",
            "inn": "123456789",
        },
        validation_flags={
            "field_errors": {},
            "warnings": {},
            "is_valid": True,
        },
    )
    db.add_all([legacy, customer_a, customer_b, recognition_b])
    await db.commit()

    headers_a = _headers(owner_a)
    headers_b = _headers(owner_b)
    me_b = await async_client.get("/api/manager/me", headers=headers_b)
    assert me_b.status_code == 200
    assert me_b.json()["tenant_id"] == tenant_b.id
    assert me_b.json()["storefront_id"] == storefront_b.id

    list_a = await async_client.get(
        "/api/manager/customers?only_with_orders=false",
        headers=headers_a,
    )
    list_b = await async_client.get(
        "/api/manager/customers?only_with_orders=false",
        headers=headers_b,
    )
    assert list_a.status_code == 200
    assert list_b.status_code == 200
    assert {item["id"] for item in list_a.json()["items"]} == {
        legacy.id,
        customer_a.id,
    }
    assert {item["id"] for item in list_b.json()["items"]} == {
        customer_b.id,
    }

    assert (
        await async_client.get(
            f"/api/manager/customers/{customer_b.id}",
            headers=headers_a,
        )
    ).status_code == 404
    assert (
        await async_client.patch(
            f"/api/manager/customers/{customer_b.id}",
            headers=headers_a,
            json={"name": "Cross-tenant write"},
        )
    ).status_code == 404
    assert (
        await async_client.delete(
            f"/api/manager/customers/{customer_b.id}",
            headers=headers_a,
        )
    ).status_code == 404

    for suffix in ("docs", "branches", "contracts", "reconciliation"):
        response = await async_client.get(
            f"/api/manager/customers/{customer_b.id}/{suffix}",
            headers=headers_a,
        )
        assert response.status_code == 404, suffix

    recognition_response = await async_client.post(
        f"/api/manager/customers/requisites/{recognition_b.id}/confirm",
        headers=headers_a,
        json={"action": "create"},
    )
    assert recognition_response.status_code == 404

    claim_legacy = await async_client.patch(
        f"/api/manager/customers/{legacy.id}",
        headers=headers_a,
        json={"name": "Legacy MVN claimed"},
    )
    assert claim_legacy.status_code == 200
    await db.refresh(legacy)
    assert legacy.tenant_id == 1


@pytest.mark.asyncio
async def test_lead_and_order_api_isolates_tenants(
    async_client: AsyncClient,
    db,
):
    tenant_b, storefront_b = await _create_tenant(db, slug="crm-b")
    owner_a = await _create_staff(
        db,
        tenant_id=1,
        username="crm-owner-a",
    )
    owner_b = await _create_staff(
        db,
        tenant_id=int(tenant_b.id),
        username="crm-owner-b",
    )

    system_customer = Customer(
        tenant_id=1,
        name="Legacy CRM customer",
        phone="+375290000011",
        type=CustomerType.individual,
    )
    customer_a = Customer(
        tenant_id=1,
        name="CRM customer A",
        phone="+375290000012",
        type=CustomerType.individual,
    )
    customer_b = Customer(
        tenant_id=int(tenant_b.id),
        name="CRM customer B",
        phone="+375290000013",
        type=CustomerType.individual,
    )
    db.add_all([system_customer, customer_a, customer_b])
    await db.flush()

    system_lead = Lead(
        tenant_id=1,
        storefront_id=1,
        source="manager",
        name="Legacy lead",
        request_text="Legacy request",
    )
    lead_a = Lead(
        tenant_id=1,
        storefront_id=1,
        source="manager",
        name="Lead A",
        request_text="Tenant A request",
    )
    lead_b = Lead(
        tenant_id=int(tenant_b.id),
        storefront_id=int(storefront_b.id),
        source="manager",
        name="Lead B",
        request_text="Tenant B request",
    )
    system_order = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=int(system_customer.id),
        status=OrderStatus.NEGOTIATION,
        title="Legacy order",
    )
    order_a = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=int(customer_a.id),
        status=OrderStatus.NEGOTIATION,
        title="Order A",
    )
    order_b = Order(
        tenant_id=int(tenant_b.id),
        storefront_id=int(storefront_b.id),
        customer_id=int(customer_b.id),
        status=OrderStatus.NEGOTIATION,
        title="Order B",
    )
    db.add_all(
        [
            system_lead,
            lead_a,
            lead_b,
            system_order,
            order_a,
            order_b,
        ]
    )
    await db.commit()

    headers_a = _headers(owner_a)
    headers_b = _headers(owner_b)

    leads_a = await async_client.get("/api/manager/leads", headers=headers_a)
    leads_b = await async_client.get("/api/manager/leads", headers=headers_b)
    assert leads_a.status_code == 200
    assert leads_b.status_code == 200
    assert {item["id"] for item in leads_a.json()["items"]} == {
        system_lead.id,
        lead_a.id,
    }
    assert {item["id"] for item in leads_b.json()["items"]} == {lead_b.id}

    orders_a = await async_client.get(
        "/api/manager/orders?segment=all",
        headers=headers_a,
    )
    orders_b = await async_client.get(
        "/api/manager/orders?segment=all",
        headers=headers_b,
    )
    assert orders_a.status_code == 200
    assert orders_b.status_code == 200
    assert {item["id"] for item in orders_a.json()["items"]} == {
        system_order.id,
        order_a.id,
    }
    assert {item["id"] for item in orders_b.json()["items"]} == {order_b.id}
    lead_cross_tenant_responses = (
        await async_client.patch(
            f"/api/manager/leads/{lead_b.id}",
            headers=headers_a,
            json={"name": "Cross-tenant lead write"},
        ),
        await async_client.post(
            f"/api/manager/leads/{lead_b.id}/mark-lost",
            headers=headers_a,
            json={"status": "lost"},
        ),
        await async_client.post(
            f"/api/manager/leads/{lead_b.id}/qualify",
            headers=headers_a,
            json={},
        ),
    )
    assert [response.status_code for response in lead_cross_tenant_responses] == [
        404,
        404,
        404,
    ]

    order_detail = await async_client.get(
        f"/api/manager/orders/{order_b.id}",
        headers=headers_a,
    )
    order_patch = await async_client.patch(
        f"/api/manager/orders/{order_b.id}",
        headers=headers_a,
        json={"comment": "Cross-tenant order write"},
    )
    order_export = await async_client.post(
        "/api/manager/orders/export",
        headers=headers_a,
        json={"order_ids": [order_b.id]},
    )
    order_delete = await async_client.delete(
        f"/api/manager/orders/{order_b.id}",
        headers=headers_a,
    )
    assert order_detail.status_code == 404
    assert order_patch.status_code == 404
    assert order_export.status_code == 400
    assert order_delete.status_code == 400

    await db.refresh(lead_b)
    await db.refresh(order_b)
    assert lead_b.name == "Lead B"
    assert str(lead_b.status) == "new"
    assert lead_b.converted_order_id is None
    assert order_b.comment is None
    assert order_b.title == "Order B"


@pytest.mark.asyncio
async def test_order_children_and_equipment_reject_foreign_tenant_ids(
    async_client: AsyncClient,
    db,
):
    tenant_b, storefront_b = await _create_tenant(db, slug="children-b")
    owner_a = await _create_staff(
        db,
        tenant_id=1,
        username="children-owner-a",
    )
    owner_b = await _create_staff(
        db,
        tenant_id=int(tenant_b.id),
        username="children-owner-b",
    )
    customer_b = Customer(
        tenant_id=int(tenant_b.id),
        name="Children customer B",
        phone="+375290000021",
        type=CustomerType.individual,
    )
    db.add(customer_b)
    await db.flush()
    order_b = Order(
        tenant_id=int(tenant_b.id),
        storefront_id=int(storefront_b.id),
        customer_id=int(customer_b.id),
        status=OrderStatus.NEGOTIATION,
        title="Children order B",
    )
    db.add(order_b)
    await db.flush()
    stage_b = OrderWorkStage(
        order_id=int(order_b.id),
        name="Foreign tenant stage",
    )
    payment_b = Payment(
        order_id=int(order_b.id),
        amount=100,
    )
    document_b = OrderDocument(
        order_id=int(order_b.id),
        doc_type="invoice",
        number="B-1",
        google_file_id="foreign-document",
        google_edit_url="https://example.invalid/foreign-document",
    )
    equipment_b = CustomerEquipment(
        customer_id=int(customer_b.id),
        source_order_id=int(order_b.id),
        display_name="Foreign tenant equipment",
        equipment_type="split",
    )
    db.add_all([stage_b, payment_b, document_b, equipment_b])
    await db.commit()

    headers_a = _headers(owner_a)
    headers_b = _headers(owner_b)

    equipment_a = await async_client.get(
        "/api/manager/equipment",
        headers=headers_a,
    )
    equipment_b_list = await async_client.get(
        "/api/manager/equipment",
        headers=headers_b,
    )
    assert equipment_a.status_code == 200
    assert equipment_b_list.status_code == 200
    assert equipment_a.json()["items"] == []
    assert {item["id"] for item in equipment_b_list.json()["items"]} == {
        equipment_b.id,
    }

    foreign_responses = (
        await async_client.patch(
            f"/api/manager/orders/work-stages/{stage_b.id}/cancel",
            headers=headers_a,
        ),
        await async_client.delete(
            f"/api/manager/orders/{order_b.id}/payments/{payment_b.id}",
            headers=headers_a,
        ),
        await async_client.get(
            f"/api/manager/orders/{order_b.id}/documents",
            headers=headers_a,
        ),
        await async_client.delete(
            f"/api/manager/docs/{document_b.id}",
            headers=headers_a,
        ),
        await async_client.get(
            f"/api/manager/orders/{order_b.id}/attachments",
            headers=headers_a,
        ),
        await async_client.get(
            f"/api/manager/orders/{order_b.id}/equipment-links",
            headers=headers_a,
        ),
        await async_client.get(
            f"/api/manager/equipment/{equipment_b.id}",
            headers=headers_a,
        ),
        await async_client.patch(
            f"/api/manager/equipment/{equipment_b.id}",
            headers=headers_a,
            json={"notes": "Cross-tenant equipment write"},
        ),
        await async_client.get(
            f"/api/manager/equipment/{equipment_b.id}/history",
            headers=headers_a,
        ),
        await async_client.get(
            f"/api/manager/equipment/{equipment_b.id}/attachments",
            headers=headers_a,
        ),
        await async_client.get(
            "/api/manager/docs/templates/contract",
            params={"order_id": order_b.id},
            headers=headers_a,
        ),
        await async_client.get(
            "/api/manager/docs/templates/contract",
            params={"customer_id": customer_b.id},
            headers=headers_a,
        ),
    )
    assert [response.status_code for response in foreign_responses] == [
        404,
        404,
        404,
        404,
        404,
        404,
        404,
        404,
        404,
        404,
        404,
        404,
    ]

    owned_order_templates = await async_client.get(
        "/api/manager/docs/templates/contract",
        params={"order_id": order_b.id},
        headers=headers_b,
    )
    owned_customer_templates = await async_client.get(
        "/api/manager/docs/templates/contract",
        params={"customer_id": customer_b.id},
        headers=headers_b,
    )
    missing_context_templates = await async_client.get(
        "/api/manager/docs/templates/contract",
        headers=headers_b,
    )
    global_templates = await async_client.get(
        "/api/manager/docs/document-templates",
        headers=headers_b,
    )
    global_template_files = await async_client.get(
        "/api/manager/docs/document-template-files",
        headers=headers_b,
    )
    assert owned_order_templates.status_code == 200
    assert owned_customer_templates.status_code == 200
    assert missing_context_templates.status_code == 403
    assert global_templates.status_code == 403
    assert global_template_files.status_code == 403

    await db.refresh(stage_b)
    await db.refresh(payment_b)
    await db.refresh(document_b)
    await db.refresh(equipment_b)
    assert str(stage_b.status) == "planned"
    assert payment_b.amount == 100
    assert document_b.number == "B-1"
    assert equipment_b.notes is None


@pytest.mark.asyncio
async def test_installer_directory_and_updates_are_tenant_scoped(
    async_client: AsyncClient,
    db,
):
    tenant_b, _ = await _create_tenant(db, slug="installer-b")
    owner_a = await _create_staff(
        db,
        tenant_id=1,
        username="installer-owner-a",
    )
    owner_b = await _create_staff(
        db,
        tenant_id=int(tenant_b.id),
        username="installer-owner-b",
    )
    legacy_installer = Installer(
        name="Legacy standalone installer",
        is_active=True,
    )
    installer_b = Installer(
        name="Tenant B legacy identity",
        is_active=True,
    )
    db.add_all([legacy_installer, installer_b])
    await db.flush()
    staff_b = StaffUser(
        display_name="Tenant B installer",
        status="active",
        primary_role="installer",
        roles=["installer"],
        username="tenant-b-installer",
        legacy_installer_id=int(installer_b.id),
    )
    db.add(staff_b)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=int(tenant_b.id),
            staff_user_id=int(staff_b.id),
            role="installer",
            status="active",
        )
    )
    await db.commit()

    headers_a = _headers(owner_a)
    headers_b = _headers(owner_b)
    list_a = await async_client.get(
        "/api/manager/installers",
        headers=headers_a,
    )
    list_b = await async_client.get(
        "/api/manager/installers",
        headers=headers_b,
    )
    assert list_a.status_code == 200
    assert list_b.status_code == 200
    assert {item["id"] for item in list_a.json()["items"]} == {
        legacy_installer.id,
    }
    assert {item["id"] for item in list_b.json()["items"]} == {installer_b.id}

    search_a = await async_client.get(
        "/api/manager/installers/search",
        params={"q": "Tenant B"},
        headers=headers_a,
    )
    search_b = await async_client.get(
        "/api/manager/installers/search",
        params={"q": "Tenant B"},
        headers=headers_b,
    )
    assert search_a.status_code == 200
    assert search_a.json()["items"] == []
    assert [item["id"] for item in search_b.json()["items"]] == [installer_b.id]

    foreign_update = await async_client.put(
        f"/api/manager/installers/{installer_b.id}",
        headers=headers_a,
        json={"name": "Cross-tenant installer write"},
    )
    assert foreign_update.status_code == 404
    await db.refresh(installer_b)
    await db.refresh(staff_b)
    assert installer_b.name == "Tenant B legacy identity"
    assert staff_b.display_name == "Tenant B installer"


@pytest.mark.asyncio
async def test_dashboard_is_tenant_scoped_and_global_mail_is_system_only(
    async_client: AsyncClient,
    db,
):
    tenant_b, storefront_b = await _create_tenant(db, slug="dashboard-b")
    owner_a = await _create_staff(
        db,
        tenant_id=1,
        username="dashboard-owner-a",
    )
    owner_b = await _create_staff(
        db,
        tenant_id=int(tenant_b.id),
        username="dashboard-owner-b",
    )
    system_customer = Customer(
        tenant_id=1,
        name="Legacy dashboard customer",
        phone="+375290000031",
        type=CustomerType.individual,
    )
    customer_a = Customer(
        tenant_id=1,
        name="Dashboard customer A",
        phone="+375290000032",
        type=CustomerType.individual,
    )
    customer_b = Customer(
        tenant_id=int(tenant_b.id),
        name="Dashboard customer B",
        phone="+375290000033",
        type=CustomerType.individual,
    )
    db.add_all([system_customer, customer_a, customer_b])
    await db.flush()
    followup_at = datetime.now() + timedelta(days=1)
    system_order = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=int(system_customer.id),
        status=OrderStatus.NEW_LEAD,
        title="Legacy dashboard order",
        next_followup_date=followup_at,
        installation_date=followup_at,
    )
    order_a = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=int(customer_a.id),
        status=OrderStatus.NEW_LEAD,
        title="Dashboard order A",
        next_followup_date=followup_at,
        installation_date=followup_at,
    )
    order_b = Order(
        tenant_id=int(tenant_b.id),
        storefront_id=int(storefront_b.id),
        customer_id=int(customer_b.id),
        status=OrderStatus.NEW_LEAD,
        title="Dashboard order B",
        next_followup_date=followup_at,
        installation_date=followup_at,
    )
    db.add_all([system_order, order_a, order_b])
    await db.commit()

    headers_a = _headers(owner_a)
    headers_b = _headers(owner_b)
    dashboard_a = await async_client.get(
        "/api/manager/dashboard/stats",
        headers=headers_a,
    )
    dashboard_b = await async_client.get(
        "/api/manager/dashboard/stats",
        headers=headers_b,
    )
    assert dashboard_a.status_code == 200
    assert dashboard_b.status_code == 200
    assert dashboard_a.json()["new_leads_count"] == 2
    assert dashboard_b.json()["new_leads_count"] == 1
    assert {
        item["order_id"] for item in dashboard_a.json()["upcoming_touchpoints"]
    } == {system_order.id, order_a.id}
    assert {
        item["order_id"] for item in dashboard_b.json()["upcoming_touchpoints"]
    } == {order_b.id}

    counter_a = await async_client.get(
        "/api/manager/leads/counter",
        headers=headers_a,
    )
    counter_b = await async_client.get(
        "/api/manager/leads/counter",
        headers=headers_b,
    )
    inbox_a = await async_client.get(
        "/api/manager/leads/inbox",
        headers=headers_a,
    )
    inbox_b = await async_client.get(
        "/api/manager/leads/inbox",
        headers=headers_b,
    )
    assert counter_a.json()["count"] == 2
    assert counter_b.json()["count"] == 1
    assert {item["id"] for item in inbox_a.json()["items"]} == {
        system_order.id,
        order_a.id,
    }
    assert {item["id"] for item in inbox_b.json()["items"]} == {order_b.id}

    calendar_params = {
        "start": (datetime.now() - timedelta(days=1)).isoformat(),
        "end": (datetime.now() + timedelta(days=2)).isoformat(),
    }
    calendar_a = await async_client.get(
        "/api/manager/calendar/events",
        params=calendar_params,
        headers=headers_a,
    )
    calendar_b = await async_client.get(
        "/api/manager/calendar/events",
        params=calendar_params,
        headers=headers_b,
    )
    assert {item["order_id"] for item in calendar_a.json()} == {
        system_order.id,
        order_a.id,
    }
    assert {item["order_id"] for item in calendar_b.json()} == {order_b.id}

    system_mail = await async_client.get(
        "/api/manager/mail/bank-receipts",
        headers=headers_a,
    )
    foreign_mail = await async_client.get(
        "/api/manager/mail/bank-receipts",
        headers=headers_b,
    )
    assert system_mail.status_code == 200
    assert foreign_mail.status_code == 403


@pytest.mark.asyncio
async def test_owner_staff_management_is_tenant_scoped(
    async_client: AsyncClient,
    db,
):
    tenant_b, _ = await _create_tenant(db, slug="staff-b")
    owner_a = await _create_staff(
        db,
        tenant_id=1,
        username="staff-owner-a",
    )
    owner_b = await _create_staff(
        db,
        tenant_id=int(tenant_b.id),
        username="staff-owner-b",
    )
    await db.commit()

    headers_a = _headers(owner_a)
    headers_b = _headers(owner_b)
    list_a = await async_client.get("/api/manager/staff", headers=headers_a)
    list_b = await async_client.get("/api/manager/staff", headers=headers_b)
    assert {item["id"] for item in list_a.json()["items"]} == {owner_a.id}
    assert {item["id"] for item in list_b.json()["items"]} == {owner_b.id}

    cross_patch = await async_client.patch(
        f"/api/manager/staff/{owner_b.id}",
        headers=headers_a,
        json={"display_name": "Must not change"},
    )
    assert cross_patch.status_code == 404

    created = await async_client.post(
        "/api/manager/staff",
        headers=headers_a,
        json={
            "display_name": "Tenant A Manager",
            "status": "active",
            "primary_role": "manager",
            "username": "tenant-a-manager",
        },
    )
    assert created.status_code == 200
    created_id = created.json()["id"]
    membership = (
        await db.execute(
            select(TenantMembership).where(
                TenantMembership.staff_user_id == created_id
            )
        )
    ).scalar_one()
    assert membership.tenant_id == 1
    assert membership.role == "manager"
    assert membership.status == "active"

    shared = await _create_staff(
        db,
        tenant_id=1,
        username="shared-staff",
    )
    db.add(
        TenantMembership(
            tenant_id=int(tenant_b.id),
            staff_user_id=int(shared.id),
            role="owner",
            status="active",
        )
    )
    await db.commit()

    shared_identity_patch = await async_client.patch(
        f"/api/manager/staff/{shared.id}",
        headers=headers_b,
        json={"display_name": "Tenant B must not rewrite shared identity"},
    )
    assert shared_identity_patch.status_code == 400

    membership_patch = await async_client.patch(
        f"/api/manager/staff/{shared.id}",
        headers=headers_b,
        json={"status": "blocked", "primary_role": "manager"},
    )
    assert membership_patch.status_code == 200
    memberships = (
        await db.execute(
            select(TenantMembership)
            .where(TenantMembership.staff_user_id == shared.id)
            .order_by(TenantMembership.tenant_id.asc())
        )
    ).scalars().all()
    assert [
        (item.tenant_id, item.role, item.status)
        for item in memberships
    ] == [
        (1, "owner", "active"),
        (tenant_b.id, "manager", "suspended"),
    ]
    await db.refresh(shared)
    assert shared.status == "active"
    assert shared.display_name == "shared-staff"


@pytest.mark.asyncio
async def test_manager_auth_uses_membership_and_fails_closed(
    async_client: AsyncClient,
    db,
):
    tenant_b, _ = await _create_tenant(db, slug="auth-b")
    membership_manager = await _create_staff(
        db,
        tenant_id=1,
        username="membership-manager",
        membership_role="manager",
        global_role="owner",
    )
    suspended = await _create_staff(
        db,
        tenant_id=1,
        username="suspended-owner",
        membership_status="suspended",
    )
    missing = await _create_staff(
        db,
        tenant_id=None,
        username="missing-membership",
    )
    ambiguous = await _create_staff(
        db,
        tenant_id=1,
        username="ambiguous-owner",
    )
    db.add(
        TenantMembership(
            tenant_id=int(tenant_b.id),
            staff_user_id=int(ambiguous.id),
            role="owner",
            status="active",
        )
    )
    await db.commit()

    manager_me = await async_client.get(
        "/api/manager/me",
        headers=_headers(membership_manager, claimed_role="owner"),
    )
    assert manager_me.status_code == 200
    assert manager_me.json()["role"] == "manager"
    assert (
        await async_client.get(
            "/api/manager/staff",
            headers=_headers(membership_manager, claimed_role="owner"),
        )
    ).status_code == 403

    for user in (suspended, missing, ambiguous):
        response = await async_client.get(
            "/api/manager/me",
            headers=_headers(user),
        )
        assert response.status_code == 403
