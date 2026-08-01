import pytest
from sqlalchemy import func
from sqlmodel import select

from core.config import settings
from models import Order, OrderProductLink, OrderStatus, Product, Storefront, Tenant
from models.supplier import Supplier, SupplyRequest, SupplyRequestLine


async def _auth_headers(async_client) -> dict[str, str]:
    response = await async_client.post(
        "/login/access-token",
        data={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _seed_scoped_order_lines(db):
    secondary_storefront = Storefront(
        id=2,
        tenant_id=1,
        slug="secondary",
        display_name="MVN Secondary",
        status="active",
        is_default=False,
    )
    foreign_tenant = Tenant(
        id=2,
        slug="foreign-supply",
        display_name="Foreign Supply",
        kind="independent_seller",
        status="active",
        is_system=False,
    )
    foreign_storefront = Storefront(
        id=3,
        tenant_id=2,
        slug="main",
        display_name="Foreign Supply Main",
        status="active",
        is_default=True,
    )
    product = Product(
        title="Scoped supply product",
        slug="scoped-supply-product",
        price=2000,
        specs={"area_m2": 25},
        is_published=True,
    )
    supplier = Supplier(
        name="Scoped supply supplier",
        code="scoped-supply-supplier",
        default_payment_method="bank",
    )
    db.add(foreign_tenant)
    await db.flush()
    db.add_all(
        [
            secondary_storefront,
            foreign_storefront,
            product,
            supplier,
        ]
    )
    await db.flush()

    orders = [
        Order(
            tenant_id=1,
            storefront_id=1,
            status=OrderStatus.NEGOTIATION,
            title="Owned order",
        ),
        Order(
            tenant_id=1,
            storefront_id=2,
            status=OrderStatus.NEGOTIATION,
            title="Foreign storefront order",
        ),
        Order(
            tenant_id=2,
            storefront_id=3,
            status=OrderStatus.NEGOTIATION,
            title="Foreign tenant order",
        ),
    ]
    db.add_all(orders)
    await db.flush()
    lines = [
        OrderProductLink(
            order_id=order.id,
            product_id=product.id,
            quantity=1,
            price=2000,
            cost=1200,
        )
        for order in orders
    ]
    db.add_all(lines)
    await db.commit()
    return supplier, lines


async def _supply_counts(db) -> tuple[int, int]:
    request_count = int(
        (await db.execute(select(func.count()).select_from(SupplyRequest))).scalar_one()
    )
    line_count = int(
        (await db.execute(select(func.count()).select_from(SupplyRequestLine))).scalar_one()
    )
    return request_count, line_count


@pytest.mark.asyncio
async def test_manager_creates_supply_request_from_owned_canonical_order_line(
    async_client,
    db,
):
    supplier, lines = await _seed_scoped_order_lines(db)

    response = await async_client.post(
        "/api/manager/supply-requests/from-order-lines",
        headers=await _auth_headers(async_client),
        json={
            "order_product_link_ids": [lines[0].id],
            "supplier_id": supplier.id,
            "intent": "order",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["lines"][0]["order_product_link_id"] == lines[0].id
    assert await _supply_counts(db) == (1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign_line_index", [1, 2])
async def test_manager_mixed_owned_and_foreign_order_lines_fail_atomically(
    async_client,
    db,
    foreign_line_index,
):
    supplier, lines = await _seed_scoped_order_lines(db)

    response = await async_client.post(
        "/api/manager/supply-requests/from-order-lines",
        headers=await _auth_headers(async_client),
        json={
            "order_product_link_ids": [lines[0].id, lines[foreign_line_index].id],
            "supplier_id": supplier.id,
            "intent": "order",
        },
    )

    assert response.status_code == 400, response.text
    assert await _supply_counts(db) == (0, 0)
