"""Database proof for tenant-scoped, side-effect-free connector projections."""

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func
from sqlmodel import select

from core.command_actor import CommandActor
from models import Customer, LeadSource, Order, OrderProposal
from models.tenancy import Storefront, Tenant, TenantScope
from services.connector_query_service import ConnectorQueryService


@pytest.mark.asyncio
async def test_connector_queries_never_repair_legacy_orders_and_keep_scope(db):
    actor = CommandActor(1, "reader", TenantScope(1, 1), "chatgpt")
    foreign = Tenant(id=2, slug="connector-foreign", display_name="Foreign")
    db.add(foreign)
    await db.flush()
    db.add(Storefront(id=2, tenant_id=2, slug="main", display_name="Foreign", status="active"))
    db.add(Storefront(id=3, tenant_id=1, slug="other", display_name="Other", status="active"))
    await db.flush()
    customer = Customer(tenant_id=1, name="Иван", phone="+375291111111")
    same_name = Customer(tenant_id=1, name="Иван", phone="+375292222222")
    foreign_customer = Customer(tenant_id=2, name="Иван", phone="+375293333333")
    db.add_all([customer, same_name, foreign_customer])
    await db.flush()
    legacy = Order(tenant_id=1, storefront_id=1, customer_id=customer.id, title="Запрос Иван")
    tender = Order(
        tenant_id=1, storefront_id=1, customer_id=customer.id, title="Перенос кондиционера",
        lead_source=LeadSource.BELZAKUPKI,
        technical_meta={"belzakupki": {"enrichment": {
            "work_summary": "Демонтировать и повторно установить одну сплит-систему.",
            "equipment_details": "Наружный и внутренний блоки заказчика.",
            "objects": [{"address": "Лепель, пл. Свободы, 11-2"}, {"address": "Лепель, пл. Свободы, 1"}],
        }}},
    )
    hidden = Order(tenant_id=2, storefront_id=2, customer_id=foreign_customer.id, title="Запрос Иван")
    other_store = Order(tenant_id=1, storefront_id=3, customer_id=customer.id, title="Запрос Иван")
    db.add_all([legacy, tender, hidden, other_store])
    await db.commit()
    own_customer_id, foreign_customer_id = customer.id, foreign_customer.id
    legacy_id, tender_id, hidden_id, other_store_id = legacy.id, tender.id, hidden.id, other_store.id
    db.expire_all()
    statements = []
    connection = await db.connection()

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(connection.sync_connection, "before_cursor_execute", observe)
    try:
        customers = await ConnectorQueryService.search_customers(db, actor, query="Иван")
        assert len(customers.items) == 2 and customers.ambiguous
        assert foreign_customer_id not in {item.id for item in customers.items}
        detail = await ConnectorQueryService.get_customer(db, actor, customer_id=own_customer_id)
        assert detail.name == "Иван" and "customerId=" in detail.link
        orders = await ConnectorQueryService.search_orders(db, actor, query="Иван")
        assert {item.id for item in orders.items} == {legacy_id, tender_id}
        order = await ConnectorQueryService.get_order(db, actor, order_id=legacy_id)
        assert order.customer_name == "Иван" and "orderId=" in order.link
        assert order.tender_review is None
        tender_order = await ConnectorQueryService.get_order(db, actor, order_id=tender_id)
        assert tender_order.tender_review.model_dump() == {
            "work_summary": "Демонтировать и повторно установить одну сплит-систему.",
            "equipment_details": "Наружный и внутренний блоки заказчика.",
            "execution_addresses": ["Лепель, пл. Свободы, 11-2", "Лепель, пл. Свободы, 1"],
        }
        for order_id in [hidden_id, other_store_id]:
            with pytest.raises(HTTPException) as failure:
                await ConnectorQueryService.get_order(db, actor, order_id=order_id)
            assert failure.value.status_code == 404
        with pytest.raises(HTTPException) as failure:
            await ConnectorQueryService.get_customer(db, actor, customer_id=foreign_customer_id)
        assert failure.value.status_code == 404
        proposal_count = (await db.execute(select(func.count(OrderProposal.id)).where(OrderProposal.order_id == legacy_id))).scalar_one()
        assert proposal_count == 0
        assert not db.new and not db.dirty and not db.deleted
        assert all(not statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for statement in statements)
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", observe)


@pytest.mark.asyncio
async def test_connector_search_treats_wildcards_as_text(db):
    actor = CommandActor(1, "reader", TenantScope(1, 1), "chatgpt")
    db.add_all([
        Customer(tenant_id=1, name="Скидка 10%", phone="+375291111111"),
        Customer(tenant_id=1, name="Любое имя", phone="+375292222222"),
    ])
    await db.commit()
    result = await ConnectorQueryService.search_customers(db, actor, query="%")
    assert [item.name for item in result.items] == ["Скидка 10%"]
    assert not result.ambiguous
