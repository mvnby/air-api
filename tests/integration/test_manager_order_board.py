"""Queue API behavior against physical isolated PostgreSQL, including stale caches."""

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import event, insert, literal, select
from sqlalchemy.orm import selectinload

from core.config import settings
from models import (
    Customer,
    CustomerType,
    Order,
    OrderProposal,
    OrderServiceLink,
    Payment,
    Product,
    Installer,
    OrderProductLink,
    OrderInstaller,
)
from models.tenancy import TenantScope
from services.order_board_projection import OrderBoardProjection

SCOPE = TenantScope(tenant_id=1, storefront_id=1)


async def page(db, **kwargs):
    return await OrderBoardProjection.page(
        db, tenant_scope=SCOPE, segment="all", **kwargs
    )


@pytest.mark.asyncio
async def test_queue_scope_null_history_dates_and_due_contacts(db):
    now = datetime.now()
    db.add_all(
        [
            Order(
                tenant_id=1,
                storefront_id=1,
                status="negotiation",
                title="active",
                next_followup_date=now - timedelta(days=1),
            ),
            Order(
                tenant_id=1,
                storefront_id=1,
                status="execution",
                title="waiting due",
                is_on_hold=True,
                next_followup_date=now - timedelta(days=1),
            ),
            Order(
                tenant_id=1,
                storefront_id=1,
                status="negotiation",
                title="waiting indefinite",
                delivery_address="Some unique address",
                is_on_hold=True,
            ),
            Order(
                tenant_id=1,
                storefront_id=1,
                status="closed",
                title="unknown",
                closing_result=None,
                closed_at=None,
                is_on_hold=True,
            ),
            Order(
                tenant_id=1,
                storefront_id=1,
                status="closed",
                title="won",
                closing_result="won",
                closed_at=now,
            ),
            Order(
                tenant_id=1,
                storefront_id=1,
                status="closed",
                title="lost",
                closing_result="lost",
                closed_at=now - timedelta(days=100),
            ),
            Order(tenant_id=1, storefront_id=1, status="new_lead", title="lead"),
        ]
    )
    await db.commit()
    active = await page(db)
    assert [i.title for i in active["items"]] == ["active"]
    assert active["queue_counts"] == {"active": 1, "waiting": 2, "history": 3, "all": 6}
    assert active["work_counts"]["followup"] == 2
    assert {
        i.title
        for i in (await page(db, queue="active", work_filter="followup"))["items"]
    } == {"active", "waiting due"}
    assert (await page(db, queue="waiting"))["total"] == 2
    history = await page(db, queue="history")
    assert history["total"] == 3
    unknown = await page(db, queue="history", result="unknown")
    assert unknown["total"] == 1 and unknown["items"][0].closed_at is None
    assert unknown["items"][0].closing_result is None
    bounded = dict(
        queue="history",
        closed_from=now.date() - timedelta(days=1),
        closed_to=now.date(),
    )
    assert (await page(db, **bounded))["total"] == 1
    assert (await page(db, **bounded, include_unknown_date=True))["total"] == 2
    assert (await page(db, queue="all", search="waiting"))["total"] == 2
    assert (await page(db, queue="all", search="unique address"))["total"] == 1
    assert (await page(db, assigned_to_me=True, staff_user_id=None))["total"] == 0


@pytest.mark.asyncio
async def test_large_history_is_not_materialized_and_groups_have_bounded_children(db):
    customer = Customer(
        tenant_id=1, name="Large customer", phone="", type=CustomerType.company
    )
    db.add(customer)
    await db.flush()
    now = datetime.now()
    # Core bulk inserts avoid constructing 10,100 ORM graphs in the fixture itself.
    await db.execute(
        insert(Order.__table__),
        [
            dict(
                tenant_id=1,
                storefront_id=1,
                customer_id=customer.id,
                status="negotiation",
                title=f"active {i}",
                created_at=now,
            )
            for i in range(100)
        ],
    )
    await db.execute(
        insert(Order.__table__),
        [
            dict(
                tenant_id=1,
                storefront_id=1,
                customer_id=customer.id,
                status="closed",
                closing_result="won",
                title=f"history {i}",
                created_at=now,
            )
            for i in range(10000)
        ],
    )
    await db.execute(
        insert(OrderServiceLink.__table__).from_select(
            ["order_id", "title", "price", "cost", "quantity"],
            select(
                Order.id,
                literal("Historical line"),
                literal(100),
                literal(50),
                literal(1),
            ).where(Order.status == "closed"),
        )
    )
    await db.execute(
        insert(Payment.__table__).from_select(
            ["order_id", "amount", "currency", "type"],
            select(Order.id, literal(50), literal("BYN"), literal("prepayment")).where(
                Order.status == "closed"
            ),
        )
    )
    await db.commit()
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))

    event.listen(db.bind.sync_engine, "before_cursor_execute", record)
    try:
        first = await page(db, limit=25)
    finally:
        event.remove(db.bind.sync_engine, "before_cursor_execute", record)
    assert len(first["items"]) == 25 and all(
        item.status == "negotiation" for item in first["items"]
    )
    assert first["total"] == 100 and first["has_more"]
    assert first["queue_counts"]["history"] == 10000
    assert not any(
        "FROM product " in sql or "FROM service " in sql for sql, _ in statements
    )
    # Actual PostgreSQL plan must fence the money relation to 100 live orders,
    # even with 10,000 historical line/payment pairs.
    money_sql, money_params = next(
        (sql, params) for sql, params in reversed(statements) if "board_money AS" in sql
    )
    connection = await db.connection()
    plan = (
        await connection.exec_driver_sql(
            "EXPLAIN (ANALYZE, FORMAT JSON) " + money_sql, money_params
        )
    ).scalar_one()
    if isinstance(plan, str):
        import json

        plan = json.loads(plan)

    def nodes(node):
        yield node
        for child in node.get("Plans", []):
            yield from nodes(child)

    fenced = [
        node
        for node in nodes(plan[0]["Plan"])
        if node.get("Subplan Name") == "CTE board_visible_orders"
    ]
    assert fenced and all(node["Actual Rows"] == 100 for node in fenced)
    assert "board_money" not in statements[0][0]  # queue count has no monetary join
    second = await page(db, page=2, limit=25)
    assert not {i.id for i in first["items"]} & {i.id for i in second["items"]}
    grouped = await page(db, group_by_customer=True)
    assert (
        grouped["items"] == []
        and grouped["total"] == 1
        and grouped["total_orders"] == 100
    )
    assert grouped["groups"][0]["count"] == 100
    children = await page(db, group_key=grouped["groups"][0]["key"], limit=25)
    assert (
        len(children["items"]) == 25
        and children["total"] == 100
        and children["has_more"]
    )
    stable = await page(db, group_by_customer=True, page=1, limit=1)
    assert stable["groups"][0]["key"] == grouped["groups"][0]["key"]


@pytest.mark.asyncio
async def test_customer_group_pagination_and_orphan_keys(db):
    customers = [
        Customer(tenant_id=1, name=f"Customer {i}", phone="") for i in range(3)
    ]
    db.add_all(customers)
    await db.flush()
    for customer in customers:
        db.add_all(
            [
                Order(
                    tenant_id=1,
                    storefront_id=1,
                    customer_id=customer.id,
                    status="negotiation",
                )
                for _ in range(3)
            ]
        )
    db.add_all(
        [Order(tenant_id=1, storefront_id=1, status="negotiation") for _ in range(2)]
    )
    await db.commit()
    first = await page(db, group_by_customer=True, limit=2)
    second = await page(db, group_by_customer=True, limit=2, page=2)
    third = await page(db, group_by_customer=True, limit=2, page=3)
    assert first["total"] == 5 and first["total_orders"] == 11
    groups = first["groups"] + second["groups"] + third["groups"]
    assert len({g["key"] for g in groups}) == 5
    assert sum(len(result["items"]) for result in [first, second, third]) == 2
    assert all(g["order_id"] is not None for g in groups if g["count"] == 1)
    assert sorted(g["count"] for g in groups) == [1, 1, 3, 3, 3]
    orphan = next(g for g in groups if g["order_id"])
    child = await page(db, group_key=orphan["key"])
    assert [o.id for o in child["items"]] == [orphan["order_id"]]


@pytest.mark.asyncio
async def test_scalar_money_matches_current_calculation_despite_stale_caches(db):
    customer = Customer(tenant_id=1, name="Money customer", phone="")
    db.add(customer)
    await db.flush()
    orders = [
        Order(
            tenant_id=1,
            storefront_id=1,
            customer_id=customer.id,
            status="negotiation",
            total_amount=99999,
            balance_due=99999,
            margin=99999,
            target_currency="USD",
            target_currency_amount=100,
        )
        for _ in range(3)
    ]
    db.add_all(orders)
    await db.flush()
    chosen = OrderProposal(
        order_id=orders[0].id, name="Chosen", is_selected=True, sort_order=10
    )
    fallback = OrderProposal(order_id=orders[1].id, name="First", sort_order=1)
    archived = OrderProposal(
        order_id=orders[2].id, name="Archived only", is_selected=True, is_archived=True
    )
    ignored = OrderProposal(order_id=orders[0].id, name="Ignored", sort_order=0)
    product = Product(title="Money product", slug="board-money-product", price=100)
    installer = Installer(name="Money installer")
    db.add_all([chosen, fallback, archived, ignored, product, installer])
    await db.flush()
    db.add(
        OrderProductLink(
            order_id=orders[0].id,
            proposal_id=chosen.id,
            product_id=product.id,
            quantity=2,
            price=100,
            cost=60,
            is_installation_included=True,
            installation_price=50,
        )
    )
    db.add(
        OrderInstaller(order_id=orders[0].id, installer_id=installer.id, agreed_pay=10)
    )
    orders[0].worker_pay_cost_byn = Decimal("5.00")
    db.add(orders[0])
    db.add_all(
        [
            OrderServiceLink(
                order_id=orders[0].id,
                proposal_id=chosen.id,
                title="Round unit",
                price=Decimal("20.125"),
                cost=Decimal("3.455"),
                quantity=10,
            ),
            OrderServiceLink(
                order_id=orders[0].id,
                proposal_id=ignored.id,
                title="Other proposal",
                price=9999,
                quantity=1,
            ),
            OrderServiceLink(
                order_id=orders[1].id,
                proposal_id=fallback.id,
                title="Fallback",
                price=100,
                quantity=1,
            ),
            OrderServiceLink(
                order_id=orders[2].id,
                proposal_id=archived.id,
                title="All-lines fallback",
                price=200,
                quantity=1,
            ),
            OrderServiceLink(
                order_id=orders[2].id,
                proposal_id=None,
                title="Orphan",
                price=50,
                quantity=1,
            ),
            Payment(
                order_id=orders[0].id, amount=150, currency="USD"
            ),  # overpaid; cannot offset sibling debt
            Payment(order_id=orders[0].id, amount=1000, currency="EUR"),  # ignored
            Payment(order_id=orders[1].id, amount=25, currency="BYN"),
        ]
    )
    await db.commit()
    order_ids = [o.id for o in orders]
    response = await page(db)
    cards = {card.id: card for card in response["items"]}
    assert (
        await db.execute(select(Order.total_amount).where(Order.id == order_ids[0]))
    ).scalar_one() == 99999
    expected = []
    for order in orders:
        actual = (
            await db.execute(
                select(Order)
                .where(Order.id == order.id)
                .options(
                    selectinload(Order.proposals),
                    selectinload(Order.product_links),
                    selectinload(Order.service_links),
                    selectinload(Order.payments),
                    selectinload(Order.installers),
                )
            )
        ).scalar_one()
        actual.calculate_totals()
        for key in (
            "total_amount",
            "total_cost",
            "total_payments",
            "balance_due",
            "margin",
            "target_currency_payments",
        ):
            assert getattr(cards[order.id], key) == pytest.approx(getattr(actual, key))
        expected.append(
            SimpleNamespace(
                total_amount=actual.total_amount,
                balance_due=actual.balance_due,
                margin=actual.margin,
            )
        )
    # Roll back the read-side in-memory calculation: the new GET must not repair caches.
    await db.rollback()
    group = (await page(db, group_by_customer=True))["groups"][0]
    for key in ("total_amount", "balance_due", "margin"):
        assert float(group[key]) == pytest.approx(
            sum(getattr(o, key) for o in expected)
        )
    assert group["balance_due"] == 325
    unpaid = await page(db, work_filter="unpaid")
    assert len(unpaid["items"]) == 2
    assert response["work_counts"]["unpaid"] == 2
    assert [o.id for o in (await page(db, sort="margin_desc"))["items"]] == [
        order_ids[2],
        order_ids[0],
        order_ids[1],
    ]


@pytest.mark.asyncio
async def test_board_endpoint_compatibility_and_limits(async_client, db):
    db.add_all(
        [
            Order(tenant_id=1, storefront_id=1, status="negotiation"),
            Order(
                tenant_id=1,
                storefront_id=1,
                status="closed",
                closed_at=None,
                closing_result=None,
            ),
        ]
    )
    await db.commit()
    login = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    old = await async_client.get("/api/manager/orders?segment=all", headers=headers)
    assert old.status_code == 200 and old.json()["meta"]["total"] == 2
    assert "closed_at" in old.json()["items"][0]
    response = await async_client.get(
        "/api/manager/orders/board?segment=all", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert (
        await async_client.get("/api/manager/orders/board?limit=101", headers=headers)
    ).status_code == 422
    assert (
        await async_client.get(
            "/api/manager/orders/board?queue=invalid", headers=headers
        )
    ).status_code == 422
    assert (
        await async_client.get(
            "/api/manager/orders/board?closed_from=2026-10-20&closed_to=2026-10-01",
            headers=headers,
        )
    ).status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("equipment_status,proposal_status", [
    (None, None), (None, "sent"), ("issued", None), ("reserved", "approved"),
])
async def test_unknown_history_preserves_legacy_nulls_and_list_status_defaults(
    async_client, db, equipment_status, proposal_status,
):
    customer = Customer(
        tenant_id=1, name="Legacy company", phone="", type=CustomerType.company,
    )
    db.add(customer)
    await db.flush()
    # Core insertion deliberately persists SQL NULL instead of ORM defaults.
    order_id = (await db.execute(
        insert(Order.__table__).values(
            tenant_id=1, storefront_id=1, customer_id=customer.id, status="closed",
            equipment_status=equipment_status, proposal_status=proposal_status,
            closing_result=None, closed_at=None, lead_source=None,
            document_role_type=None, target_currency=None,
        ).returning(Order.id)
    )).scalar_one()
    await db.commit()
    stored = select(
        Order.equipment_status, Order.proposal_status, Order.closing_result, Order.closed_at,
    ).where(Order.id == order_id)
    before = (await db.execute(stored)).one()
    assert tuple(before) == (equipment_status, proposal_status, None, None)
    login = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    legacy = await async_client.get("/api/manager/orders?segment=b2b", headers=headers)
    assert legacy.status_code == 200, legacy.text
    expected = legacy.json()["items"][0]
    assert expected["equipment_status"] == (equipment_status or "pending")
    assert expected["proposal_status"] == (proposal_status or "draft")
    params = dict(
        segment="b2b", queue="history", assigned_to_me=False, work_filter="all",
        result="unknown", include_unknown_date=False, sort="closed_at_desc", page=1, limit=25,
    )
    for grouped in (False, True):
        response = await async_client.get(
            "/api/manager/orders/board", headers=headers,
            params={**params, "group_by_customer": grouped},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["total_orders"] == 1 and payload["total"] == 1
        assert len(payload["items"]) == 1
        card = payload["items"][0]
        assert card["id"] == order_id and card["status"] == "closed"
        assert card["equipment_status"] == expected["equipment_status"]
        assert card["proposal_status"] == expected["proposal_status"]
        assert card["closing_result"] is None and card["closed_at"] is None
        assert card["lead_source"] is None and card["document_role_type"] is None
        assert card["target_currency"] is None
    bounded = await async_client.get(
        "/api/manager/orders/board", headers=headers,
        params={**params, "closed_from": "2026-10-01"},
    )
    assert bounded.status_code == 200 and bounded.json()["total"] == 0
    assert (await db.execute(stored)).one() == before


@pytest.mark.asyncio
async def test_visibility_segment_customer_and_column_filters_are_shared(db):
    from models.tenancy import Tenant, Storefront, TenantMembership
    from models import StaffUser

    other = Tenant(slug="board-other", display_name="Other")
    db.add(other)
    await db.flush()
    other_site = Storefront(
        tenant_id=other.id, slug="board-other", display_name="Other", status="active"
    )
    sibling_site = Storefront(
        tenant_id=1, slug="board-sibling", display_name="Sibling", status="active"
    )
    db.add_all([other_site, sibling_site])
    await db.flush()
    business = Customer(
        tenant_id=1,
        type=CustomerType.individual_entrepreneur,
        name="Business",
        phone="",
    )
    retail = Customer(tenant_id=1, name="Retail", phone="")
    foreign = Customer(
        tenant_id=other.id, type=CustomerType.company, name="Foreign", phone=""
    )
    staff = StaffUser(display_name="Board owner", username="board-owner")
    db.add_all([business, retail, foreign, staff])
    await db.flush()
    db.add(TenantMembership(tenant_id=1, staff_user_id=staff.id, role="manager"))
    await db.flush()
    db.add_all(
        [
            Order(
                tenant_id=1,
                storefront_id=1,
                customer_id=business.id,
                status="negotiation",
                negotiation_status="follow_up",
                responsible_staff_user_id=staff.id,
            ),
            Order(
                tenant_id=1,
                storefront_id=1,
                customer_id=business.id,
                status="negotiation",
                negotiation_status="awaiting_offer",
            ),
            Order(
                tenant_id=1, storefront_id=1, customer_id=retail.id, status="execution"
            ),
            Order(
                tenant_id=1,
                storefront_id=sibling_site.id,
                customer_id=business.id,
                status="negotiation",
            ),
            Order(
                tenant_id=other.id,
                storefront_id=other_site.id,
                customer_id=foreign.id,
                status="negotiation",
            ),
        ]
    )
    await db.commit()
    visible = await page(db)
    assert visible["total"] == 3 and visible["queue_counts"]["all"] == 3
    b2b = await OrderBoardProjection.page(
        db, tenant_scope=SCOPE, segment="b2b", group_by_customer=True
    )
    assert b2b["total"] == 1 and b2b["total_orders"] == 2
    assert (await page(db, customer_id=foreign.id))["total"] == 0
    assert (await page(db, group_key=f"customer:{foreign.id}"))["total"] == 0
    assert (await page(db, customer_id=business.id))["total"] == 2
    assert (await page(db, assigned_to_me=True, staff_user_id=staff.id))["total"] == 1
    phase = await page(db, column="negotiation", phase="follow_up")
    assert phase["total"] == 1 and phase["queue_counts"]["active"] == 3
    demo = await OrderBoardProjection.page(
        db,
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1, demo_read_only=True),
        segment="all",
    )
    assert all(
        card.margin is None
        and card.total_cost is None
        and card.installer_cost_byn is None
        for card in demo["items"]
    )
