from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import select

from core.security import create_access_token
from models import (
    Customer,
    Lead,
    Order,
    OrderDocument,
    OrderProductLink,
    OrderStatus,
    OrderWorkStage,
    Product,
    StaffUser,
    Storefront,
    TenantMembership,
)
from models.common import CustomerType
from services.manager_storefront_selector_service import MANAGER_STOREFRONT_HEADER


async def _create_owner(db, *, username: str) -> StaffUser:
    owner = StaffUser(
        display_name=username,
        status="active",
        roles=["owner"],
        primary_role="owner",
        username=username,
    )
    db.add(owner)
    await db.flush()
    db.add(
        TenantMembership(
            tenant_id=1,
            staff_user_id=int(owner.id),
            role="owner",
            status="active",
        )
    )
    await db.flush()
    return owner


def _headers(
    owner: StaffUser,
    *,
    storefront_slug: str | None = None,
) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": owner.username,
            "staff_user_id": owner.id,
            "auth_source": "storefront-crm-isolation-test",
        },
        expires_delta=timedelta(minutes=10),
    )
    headers = {"Authorization": f"Bearer {token}"}
    if storefront_slug is not None:
        headers[MANAGER_STOREFRONT_HEADER] = storefront_slug
    return headers


async def _create_orsha(db) -> Storefront:
    storefront = Storefront(
        id=2,
        tenant_id=1,
        slug="orsha",
        display_name="MVN Орша",
        status="active",
        city="Орша",
        is_default=False,
    )
    db.add(storefront)
    await db.flush()
    return storefront


@pytest.mark.asyncio
async def test_manager_crm_reads_and_mutations_are_exactly_storefront_scoped(
    async_client: AsyncClient,
    db,
):
    owner = await _create_owner(db, username="crm-storefront-owner")
    orsha = await _create_orsha(db)
    customer = Customer(
        tenant_id=1,
        name="Общий клиент",
        phone="+375290000091",
        type=CustomerType.individual,
    )
    product = Product(
        title="Storefront isolation product",
        slug="storefront-isolation-product",
        price=100,
    )
    db.add_all([customer, product])
    await db.flush()

    main_order = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=int(customer.id),
        status=OrderStatus.NEGOTIATION,
        title="Минский заказ",
        delivery_address="Минск",
        total_amount=100,
    )
    main_inbox = Order(
        tenant_id=1,
        storefront_id=1,
        customer_id=int(customer.id),
        status=OrderStatus.NEW_LEAD,
        title="Минская заявка",
    )
    orsha_order = Order(
        tenant_id=1,
        storefront_id=int(orsha.id),
        customer_id=int(customer.id),
        status=OrderStatus.NEGOTIATION,
        title="Оршанский заказ",
        delivery_address="Орша",
        total_amount=900,
    )
    orsha_inbox = Order(
        tenant_id=1,
        storefront_id=int(orsha.id),
        customer_id=int(customer.id),
        status=OrderStatus.NEW_LEAD,
        title="Оршанская заявка",
    )
    main_lead = Lead(
        tenant_id=1,
        storefront_id=1,
        source="manager",
        name="Минский лид",
        request_text="Минский запрос",
    )
    orsha_lead = Lead(
        tenant_id=1,
        storefront_id=int(orsha.id),
        source="manager",
        name="Оршанский лид",
        request_text="Оршанский запрос",
    )
    db.add_all(
        [
            main_order,
            main_inbox,
            orsha_order,
            orsha_inbox,
            main_lead,
            orsha_lead,
        ]
    )
    await db.flush()
    db.add_all(
        [
            OrderProductLink(
                order_id=int(main_order.id),
                product_id=int(product.id),
                quantity=1,
                price=100,
                cost=50,
            ),
            OrderProductLink(
                order_id=int(orsha_order.id),
                product_id=int(product.id),
                quantity=1,
                price=900,
                cost=450,
            ),
        ]
    )
    main_document = OrderDocument(
        order_id=int(main_order.id),
        doc_type="invoice",
        number="MAIN-1",
        google_file_id="main-document",
        google_edit_url="https://example.invalid/main-document",
    )
    orsha_document = OrderDocument(
        order_id=int(orsha_order.id),
        doc_type="invoice",
        number="ORSHA-1",
        google_file_id="orsha-document",
        google_edit_url="https://example.invalid/orsha-document",
    )
    orsha_stage = OrderWorkStage(
        order_id=int(orsha_order.id),
        name="Оршанский этап",
    )
    db.add_all([main_document, orsha_document, orsha_stage])
    await db.commit()

    main_headers = _headers(owner)
    orsha_headers = _headers(owner, storefront_slug="orsha")

    main_orders = await async_client.get(
        "/api/manager/orders?segment=all",
        headers=main_headers,
    )
    orsha_orders = await async_client.get(
        "/api/manager/orders?segment=all",
        headers=orsha_headers,
    )
    assert main_orders.status_code == 200
    assert orsha_orders.status_code == 200
    assert {item["id"] for item in main_orders.json()["items"]} == {main_order.id}
    assert {item["id"] for item in orsha_orders.json()["items"]} == {
        orsha_order.id
    }

    main_leads = await async_client.get("/api/manager/leads", headers=main_headers)
    orsha_leads = await async_client.get(
        "/api/manager/leads",
        headers=orsha_headers,
    )
    assert {item["id"] for item in main_leads.json()["items"]} == {main_lead.id}
    assert {item["id"] for item in orsha_leads.json()["items"]} == {orsha_lead.id}

    for headers, expected_order_id in (
        (main_headers, main_inbox.id),
        (orsha_headers, orsha_inbox.id),
    ):
        counter = await async_client.get("/api/manager/leads/counter", headers=headers)
        inbox = await async_client.get("/api/manager/leads/inbox", headers=headers)
        dashboard = await async_client.get(
            "/api/manager/dashboard/stats",
            headers=headers,
        )
        assert counter.json() == {"count": 1, "has_new": True}
        assert [item["id"] for item in inbox.json()["items"]] == [expected_order_id]
        assert dashboard.json()["new_leads_count"] == 1

    main_customer = await async_client.get(
        f"/api/manager/customers/{customer.id}",
        headers=main_headers,
    )
    orsha_customer = await async_client.get(
        f"/api/manager/customers/{customer.id}",
        headers=orsha_headers,
    )
    assert main_customer.json()["order_count"] == 2
    assert main_customer.json()["last_delivery_address"] == "Минск"
    assert orsha_customer.json()["order_count"] == 2
    assert orsha_customer.json()["last_delivery_address"] == "Орша"

    main_docs = await async_client.get(
        f"/api/manager/customers/{customer.id}/docs",
        headers=main_headers,
    )
    orsha_docs = await async_client.get(
        f"/api/manager/customers/{customer.id}/docs",
        headers=orsha_headers,
    )
    assert [item["id"] for item in main_docs.json()["items"]] == [main_document.id]
    assert [item["id"] for item in orsha_docs.json()["items"]] == [orsha_document.id]

    main_reconciliation = await async_client.get(
        f"/api/manager/customers/{customer.id}/reconciliation",
        headers=main_headers,
    )
    orsha_reconciliation = await async_client.get(
        f"/api/manager/customers/{customer.id}/reconciliation",
        headers=orsha_headers,
    )
    assert main_reconciliation.json()["documents_total"] == 100
    assert orsha_reconciliation.json()["documents_total"] == 900

    foreign_responses = (
        await async_client.get(
            f"/api/manager/orders/{orsha_order.id}",
            headers=main_headers,
        ),
        await async_client.patch(
            f"/api/manager/orders/{orsha_order.id}",
            headers=main_headers,
            json={"comment": "Чужое изменение"},
        ),
        await async_client.delete(
            f"/api/manager/orders/{orsha_order.id}",
            headers=main_headers,
        ),
        await async_client.post(
            "/api/manager/orders/export",
            headers=main_headers,
            json={"order_ids": [main_order.id, orsha_order.id]},
        ),
        await async_client.patch(
            f"/api/manager/orders/work-stages/{orsha_stage.id}/cancel",
            headers=main_headers,
        ),
        await async_client.patch(
            f"/api/manager/leads/{orsha_lead.id}",
            headers=main_headers,
            json={"name": "Чужой лид"},
        ),
        await async_client.post(
            f"/api/manager/leads/{orsha_lead.id}/mark-lost",
            headers=main_headers,
            json={"status": "lost"},
        ),
        await async_client.post(
            f"/api/manager/leads/{orsha_lead.id}/qualify",
            headers=main_headers,
            json={},
        ),
    )
    assert [response.status_code for response in foreign_responses] == [
        404,
        404,
        400,
        400,
        404,
        404,
        404,
        404,
    ]

    await db.refresh(orsha_order)
    await db.refresh(orsha_stage)
    await db.refresh(orsha_lead)
    assert orsha_order.comment is None
    assert orsha_stage.status == "planned"
    assert orsha_lead.name == "Оршанский лид"
    assert str(orsha_lead.status) == "new"
    assert orsha_lead.converted_order_id is None


@pytest.mark.asyncio
async def test_lead_qualification_keeps_exact_storefront_and_replay_boundary(
    async_client: AsyncClient,
    db,
):
    owner = await _create_owner(db, username="qualification-storefront-owner")
    orsha = await _create_orsha(db)
    lead = Lead(
        tenant_id=1,
        storefront_id=int(orsha.id),
        source="manager",
        name="Лид из Орши",
        phone="+375290000092",
        request_text="Нужен кондиционер",
    )
    db.add(lead)
    await db.commit()

    orsha_headers = _headers(owner, storefront_slug="orsha")
    qualified = await async_client.post(
        f"/api/manager/leads/{lead.id}/qualify",
        headers=orsha_headers,
        json={"order_comment": "Квалифицирован в Орше"},
    )
    assert qualified.status_code == 200, qualified.text

    order = await db.get(Order, qualified.json()["order_id"])
    assert order is not None
    assert (order.tenant_id, order.storefront_id) == (1, orsha.id)

    replay_in_orsha = await async_client.post(
        f"/api/manager/leads/{lead.id}/qualify",
        headers=orsha_headers,
        json={},
    )
    replay_in_main = await async_client.post(
        f"/api/manager/leads/{lead.id}/qualify",
        headers=_headers(owner),
        json={},
    )
    assert replay_in_orsha.status_code == 200
    assert replay_in_orsha.json()["order_id"] == order.id
    assert replay_in_main.status_code == 404
    storefront_orders = list(
        (
            await db.execute(
                select(Order).where(Order.storefront_id == int(orsha.id))
            )
        ).scalars()
    )
    assert [item.id for item in storefront_orders] == [order.id]
