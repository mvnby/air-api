"""Manual goods are proposal snapshots, never synthetic catalog products."""
import pytest
from sqlmodel import select
from core.config import settings
from models import Customer, Order, OrderProductLink, OrderProposal, OrderStatus, Product
from modules.documents.application.commercial_rows import line_rows
from services.documents.standard import GeneralDocStrategy


@pytest.mark.asyncio
async def test_manual_goods_roundtrip_scope_documents_and_catalog_replacement(async_client, db):
    customer = Customer(tenant_id=1, name="Manual goods customer", phone="")
    product = Product(title="Catalog neighbour", slug="manual-goods-neighbour", price=1000)
    db.add_all([customer, product])
    await db.flush()
    order = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.flush()
    first = OrderProposal(order_id=order.id, name="First", is_selected=True)
    second = OrderProposal(order_id=order.id, name="Alternative", is_selected=False)
    db.add_all([first, second])
    await db.flush()
    neighbour = OrderProductLink(order_id=order.id, proposal_id=first.id, product_id=product.id, quantity=1, price=1000, cost=700)
    alternative = OrderProductLink(order_id=order.id, proposal_id=second.id, product_id=product.id, quantity=3, price=2000, cost=500)
    db.add_all([neighbour, alternative])
    await db.commit()
    login = await async_client.post("/login/access-token", data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    endpoint = f"/api/manager/orders/{order.id}"
    title = "Декоративный экран для кондиционера"
    payload = {"line_proposal_id": first.id, "products": [
        {"link_id": neighbour.id, "product_id": product.id, "quantity": 1, "price": 1000, "cost": 700},
        {"product_id": None, "title": f"  {title}  ", "client_description": "Белый, по размеру клиента", "quantity": 2, "price": 350, "cost": 200},
    ]}
    response = await async_client.patch(endpoint, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    reopened = (await async_client.get(endpoint, headers=headers)).json()
    assert len(reopened["service_lines"]) == 0
    manual = next(line for line in reopened["product_lines"] if line["product_id"] is None)
    assert (manual["product_title"], manual["quantity"], manual["price"], manual["cost"]) == (title, 2, 350, 200)
    assert manual["catalog_price"] is None
    assert manual["product_country"] is None
    assert manual["product_logistics_components"] == []
    assert reopened["total_amount"] == 1700
    assert reopened["total_cost"] == 1100
    other = next(p for p in reopened["proposals"] if p["id"] == second.id)
    assert [(line["id"], line["quantity"], line["price"]) for line in other["product_lines"]] == [(alternative.id, 3, 2000)]
    assert list((await db.execute(select(Product))).scalars()) == [product]
    stored = await db.get(OrderProductLink, manual["id"], populate_existing=True)
    stored.product = None
    native = line_rows([stored], [])
    assert native[0]["line.kind"] == "product"
    assert native[0]["line.title"] == f"{title}\nБелый, по размеру клиента"
    assert native[0]["line.amount"] == "700.00"
    legacy_order = type("DocumentOrder", (), {"product_links": [stored], "service_links": []})()
    strategy = object.__new__(GeneralDocStrategy)
    strategy.order = legacy_order
    legacy = strategy._prepare_table_data()
    assert legacy[0][1] == native[0]["line.title"]
    assert legacy[0][-1] == "700.00"
    # Replay of the same manual ID updates its snapshot without duplicating it.
    payload["products"][1].update(link_id=manual["id"], title="Экран по согласованному чертежу")
    replay = await async_client.patch(endpoint, headers=headers, json=payload)
    assert replay.status_code == 200, replay.text
    assert len(replay.json()["product_lines"]) == 2
    # A real catalog selection clears the old manual title and preserves line identity.
    payload["products"][1].update(product_id=product.id)
    linked = await async_client.patch(endpoint, headers=headers, json=payload)
    assert linked.status_code == 200, linked.text
    changed = next(line for line in linked.json()["product_lines"] if line["id"] == manual["id"])
    assert changed["product_id"] == product.id
    assert changed["title_snapshot"] is None
    assert changed["product_title"] == product.title
    # Manual rows cannot claim a link from a different proposal.
    payload["products"][1].update(link_id=alternative.id, product_id=None)
    forbidden = await async_client.patch(endpoint, headers=headers, json=payload)
    assert forbidden.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("line", [
    {"title": " "}, {"title": "Good", "quantity": 0},
    {"title": "Good", "price": -1}, {"title": "Good", "cost": -1},
    {"title": "Good", "price": 10.5}, {"title": "Good", "product_id": 0},
])
async def test_manual_goods_reject_invalid_data(async_client, db, line):
    order = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.commit()
    login = await async_client.post("/login/access-token", data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    order_id = order.id
    response = await async_client.patch(f"/api/manager/orders/{order_id}", headers=headers, json={"products": [{"product_id": None, "quantity": 1, "price": 100, "cost": 50, **line}]})
    assert response.status_code in (400, 422), response.text
    assert not list((await db.execute(select(OrderProductLink).where(OrderProductLink.order_id == order_id))).scalars())
