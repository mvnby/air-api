from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Customer, Order, OrderProductLink, OrderProposal, OrderStatus, Product
from models.tenancy import TenantScope
from schemas import OrderProposalCreatePayload, OrderProposalUpdatePayload
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_service import OrderService
from services.catalog_decision_projection import (
    CatalogDecisionProductSnapshot,
    CatalogDecisionQueryService,
)
from services.catalog_decision_order_service import (
    CatalogDecisionOrderConflict,
    CatalogDecisionOrderService,
)


TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def proposal_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'order_proposal_commands.db'}",
        echo=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _create_order(session: AsyncSession) -> int:
    customer = Customer(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        name="Proposal transaction customer",
        phone="+375290000001",
    )
    session.add(customer)
    await session.flush()
    order = Order(
        tenant_id=TEST_TENANT_SCOPE.tenant_id,
        storefront_id=TEST_TENANT_SCOPE.storefront_id,
        customer_id=customer.id,
        status=OrderStatus.NEGOTIATION,
    )
    session.add(order)
    await session.commit()
    return int(order.id)


async def _fail_after_proposal_flush(
    _session: AsyncSession,
    _order: Order,
) -> None:
    raise RuntimeError("injected final-step failure")


async def _create_products(session: AsyncSession) -> list[Product]:
    products = [
        Product(title="Gree 12", slug="gree-12", price=2200),
        Product(title="MDV 18", slug="mdv-18", price=3100),
    ]
    session.add_all(products)
    await session.commit()
    return products


def _stub_catalog_snapshots(monkeypatch: pytest.MonkeyPatch, products: list[Product]) -> None:
    async def resolve(_cls, _session, *, tenant_scope, product_ids):
        assert tenant_scope == TEST_TENANT_SCOPE
        by_id = {int(product.id): product for product in products}
        return {
            product_id: CatalogDecisionProductSnapshot(
                product=by_id[product_id],
                retail_price_byn=int(by_id[product_id].price),
                purchase_cost_byn=1000 + product_id,
            )
            for product_id in product_ids
            if product_id in by_id
        }

    monkeypatch.setattr(
        CatalogDecisionQueryService,
        "get_system_product_snapshots",
        classmethod(resolve),
    )


@pytest.mark.asyncio
async def test_create_proposal_rolls_back_default_and_new_proposal_together(
    proposal_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id = await _create_order(proposal_session)
    monkeypatch.setattr(
        OrderService,
        "_refresh_order_financials",
        _fail_after_proposal_flush,
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderProposalCommandService.create_order_proposal(
            proposal_session,
            order_id,
            OrderProposalCreatePayload(name="Новый вариант"),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    proposals = list(
        (
            await proposal_session.execute(
                select(OrderProposal).where(OrderProposal.order_id == order_id)
            )
        )
        .scalars()
        .all()
    )
    assert proposals == []


@pytest.mark.asyncio
async def test_update_proposal_rolls_back_flushed_fields(
    proposal_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id = await _create_order(proposal_session)
    proposal = OrderProposal(
        order_id=order_id,
        name="Исходный вариант",
        status="draft",
        is_selected=True,
        sort_order=0,
    )
    proposal_session.add(proposal)
    await proposal_session.commit()
    proposal_id = int(proposal.id)
    monkeypatch.setattr(
        OrderService,
        "_refresh_order_financials",
        _fail_after_proposal_flush,
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderProposalCommandService.update_order_proposal(
            proposal_session,
            order_id,
            proposal_id,
            OrderProposalUpdatePayload(name="Не должно сохраниться"),
            tenant_scope=TEST_TENANT_SCOPE,
        )

    stored = await proposal_session.get(OrderProposal, proposal_id)
    assert stored is not None
    assert stored.name == "Исходный вариант"


@pytest.mark.asyncio
async def test_select_proposal_rolls_back_all_selection_changes(
    proposal_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id = await _create_order(proposal_session)
    first = OrderProposal(
        order_id=order_id,
        name="Первый",
        status="draft",
        is_selected=True,
        sort_order=0,
    )
    second = OrderProposal(
        order_id=order_id,
        name="Второй",
        status="draft",
        is_selected=False,
        sort_order=10,
    )
    proposal_session.add_all([first, second])
    await proposal_session.commit()
    first_id = int(first.id)
    second_id = int(second.id)
    monkeypatch.setattr(
        OrderService,
        "_refresh_order_financials",
        _fail_after_proposal_flush,
    )

    with pytest.raises(RuntimeError, match="injected final-step failure"):
        await OrderProposalCommandService.select_order_proposal(
            proposal_session,
            order_id,
            second_id,
            tenant_scope=TEST_TENANT_SCOPE,
        )

    stored = list(
        (
            await proposal_session.execute(
                select(OrderProposal)
                .where(OrderProposal.order_id == order_id)
                .order_by(OrderProposal.sort_order)
            )
        )
        .scalars()
        .all()
    )
    assert [(item.id, item.is_selected) for item in stored] == [
        (first_id, True),
        (second_id, False),
    ]


@pytest.mark.asyncio
async def test_catalog_selection_fills_empty_main_proposal(
    proposal_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id = await _create_order(proposal_session)
    products = await _create_products(proposal_session)
    _stub_catalog_snapshots(monkeypatch, products)

    detail = await CatalogDecisionOrderService.attach(
        proposal_session,
        order_id=order_id,
        product_ids=[int(product.id) for product in products],
        mode="auto",
        tenant_scope=TEST_TENANT_SCOPE,
    )

    assert len(detail["proposals"]) == 1
    assert detail["proposals"][0]["name"] == "Основное"
    assert detail["proposals"][0]["is_selected"] is True
    assert [line["product_id"] for line in detail["proposals"][0]["product_lines"]] == [
        int(product.id) for product in products
    ]


@pytest.mark.asyncio
async def test_catalog_selection_requires_choice_and_preserves_existing_lines(
    proposal_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id = await _create_order(proposal_session)
    products = await _create_products(proposal_session)
    first_product_id = int(products[0].id)
    second_product_id = int(products[1].id)
    _stub_catalog_snapshots(monkeypatch, products)
    proposal = OrderProposal(order_id=order_id, name="Основное", is_selected=True)
    proposal_session.add(proposal)
    await proposal_session.flush()
    existing = OrderProductLink(
        order_id=order_id,
        proposal_id=int(proposal.id),
        product_id=first_product_id,
        quantity=1,
        price=2200,
        cost=900,
    )
    proposal_session.add(existing)
    await proposal_session.commit()

    with pytest.raises(
        CatalogDecisionOrderConflict,
        match="Выберите замену",
    ):
        await CatalogDecisionOrderService.attach(
            proposal_session,
            order_id=order_id,
            product_ids=[second_product_id],
            mode="auto",
            tenant_scope=TEST_TENANT_SCOPE,
        )

    stored = list(
        (
            await proposal_session.execute(
                select(OrderProductLink).where(OrderProductLink.order_id == order_id)
            )
        ).scalars().all()
    )
    assert [(line.product_id, line.price) for line in stored] == [(first_product_id, 2200)]


@pytest.mark.asyncio
async def test_catalog_selection_creates_unselected_alternative_without_overwriting_main(
    proposal_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id = await _create_order(proposal_session)
    products = await _create_products(proposal_session)
    _stub_catalog_snapshots(monkeypatch, products)
    main = OrderProposal(order_id=order_id, name="Основное", is_selected=True, sort_order=0)
    proposal_session.add(main)
    await proposal_session.flush()
    proposal_session.add(OrderProductLink(
        order_id=order_id,
        proposal_id=int(main.id),
        product_id=int(products[0].id),
        quantity=1,
        price=2200,
        cost=900,
    ))
    await proposal_session.commit()

    detail = await CatalogDecisionOrderService.attach(
        proposal_session,
        order_id=order_id,
        product_ids=[int(products[1].id)],
        mode="new_alternative",
        tenant_scope=TEST_TENANT_SCOPE,
    )

    assert len(detail["proposals"]) == 2
    selected = next(item for item in detail["proposals"] if item["is_selected"])
    alternative = next(item for item in detail["proposals"] if not item["is_selected"])
    assert [line["product_id"] for line in selected["product_lines"]] == [int(products[0].id)]
    assert [line["product_id"] for line in alternative["product_lines"]] == [int(products[1].id)]
    assert alternative["name"] == "Вариант 2"


@pytest.mark.asyncio
async def test_catalog_selection_replaces_only_selected_proposal_when_confirmed(
    proposal_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    order_id = await _create_order(proposal_session)
    products = await _create_products(proposal_session)
    _stub_catalog_snapshots(monkeypatch, products)
    main = OrderProposal(order_id=order_id, name="Основное", is_selected=True, sort_order=0)
    alternative = OrderProposal(order_id=order_id, name="Сохранить", is_selected=False, sort_order=10)
    proposal_session.add_all([main, alternative])
    await proposal_session.flush()
    proposal_session.add_all([
        OrderProductLink(order_id=order_id, proposal_id=int(main.id), product_id=int(products[0].id), price=2200, cost=900),
        OrderProductLink(order_id=order_id, proposal_id=int(alternative.id), product_id=int(products[0].id), price=2100, cost=850),
    ])
    await proposal_session.commit()

    detail = await CatalogDecisionOrderService.attach(
        proposal_session,
        order_id=order_id,
        product_ids=[int(products[1].id)],
        mode="replace_selected",
        tenant_scope=TEST_TENANT_SCOPE,
    )

    selected = next(item for item in detail["proposals"] if item["is_selected"])
    saved_alternative = next(item for item in detail["proposals"] if item["name"] == "Сохранить")
    assert [line["product_id"] for line in selected["product_lines"]] == [int(products[1].id)]
    assert [line["product_id"] for line in saved_alternative["product_lines"]] == [int(products[0].id)]
