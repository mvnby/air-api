from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import (
    GlobalConfig,
    InstallationDiscountPolicy,
    InstallationDiscountProductRule,
    Product,
)
from schemas_manager_installation_discounts import ManagerInstallationDiscountStatus
from services.installation_discount_service import InstallationDiscountService


@pytest.fixture
async def discount_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'discounts.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


async def _products(session: AsyncSession, count: int) -> list[Product]:
    products = [
        Product(
            title=f"Conditioner {index}",
            slug=f"conditioner-{index}",
            price=2_000,
            is_published=True,
        )
        for index in range(count)
    ]
    session.add_all(products)
    await session.commit()
    for product in products:
        await session.refresh(product)
    return products


@pytest.mark.asyncio
async def test_disabled_policy_preserves_live_legacy_discount(discount_session):
    product = (await _products(discount_session, 1))[0]
    discount_session.add_all(
        [
            GlobalConfig(key="install_discount", value="100"),
            InstallationDiscountPolicy(
                id=1,
                is_enabled=False,
                default_discount=250,
                minimum_margin=350,
            ),
            InstallationDiscountProductRule(
                product_id=int(product.id),
                discount_amount=0,
            ),
        ]
    )
    await discount_session.commit()

    decision = (
        await InstallationDiscountService.resolve_for_products(
            discount_session,
            products=[product],
            effective_prices={int(product.id): 1_700},
            supply_metrics={int(product.id): {"min_cost_byn": 1_600}},
        )
    )[int(product.id)]

    assert decision.status == ManagerInstallationDiscountStatus.legacy
    assert decision.source == "legacy_global"
    assert decision.configured_discount == 0
    assert decision.applied_discount == 100
    assert decision.purchase_cost is None
    assert decision.margin is None

    manager_preview = (
        await InstallationDiscountService.resolve_for_products(
            discount_session,
            products=[product],
            effective_prices={int(product.id): 1_700},
            supply_metrics={int(product.id): {"min_cost_byn": 1_600}},
            include_economics=True,
        )
    )[int(product.id)]
    assert manager_preview.applied_discount == 100
    assert manager_preview.purchase_cost == 1_600
    assert manager_preview.margin == 100


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_cost", [None, -1, float("nan"), "bad-cost"])
async def test_enabled_policy_gates_default_discount_by_margin_and_cost(
    discount_session,
    invalid_cost,
):
    eligible, low_margin, missing_cost = await _products(discount_session, 3)
    discount_session.add(
        InstallationDiscountPolicy(
            id=1,
            is_enabled=True,
            default_discount=100,
            minimum_margin=350,
        )
    )
    await discount_session.commit()

    decisions = await InstallationDiscountService.resolve_for_products(
        discount_session,
        products=[eligible, low_margin, missing_cost],
        effective_prices={
            int(eligible.id): 2_000,
            int(low_margin.id): 1_900,
            int(missing_cost.id): 2_000,
        },
        supply_metrics={
            int(eligible.id): {"min_cost_byn": 1_600},
            int(low_margin.id): {"min_cost_byn": 1_600},
            int(missing_cost.id): {"min_cost_byn": invalid_cost},
        },
    )

    eligible_decision = decisions[int(eligible.id)]
    assert eligible_decision.status == ManagerInstallationDiscountStatus.active
    assert eligible_decision.margin == 400
    assert eligible_decision.applied_discount == 100

    low_margin_decision = decisions[int(low_margin.id)]
    assert (
        low_margin_decision.status
        == ManagerInstallationDiscountStatus.blocked_low_margin
    )
    assert low_margin_decision.margin == 300
    assert low_margin_decision.applied_discount == 0

    missing_cost_decision = decisions[int(missing_cost.id)]
    assert (
        missing_cost_decision.status
        == ManagerInstallationDiscountStatus.blocked_missing_cost
    )
    assert missing_cost_decision.applied_discount == 0


@pytest.mark.asyncio
async def test_product_overrides_change_amount_but_do_not_bypass_margin_gate(
    discount_session,
):
    custom, disabled, low_margin = await _products(discount_session, 3)
    discount_session.add(
        InstallationDiscountPolicy(
            id=1,
            is_enabled=True,
            default_discount=100,
            minimum_margin=350,
        )
    )
    discount_session.add_all(
        [
            InstallationDiscountProductRule(
                product_id=int(custom.id),
                discount_amount=300,
            ),
            InstallationDiscountProductRule(
                product_id=int(disabled.id),
                discount_amount=0,
            ),
            InstallationDiscountProductRule(
                product_id=int(low_margin.id),
                discount_amount=150,
            ),
        ]
    )
    await discount_session.commit()

    decisions = await InstallationDiscountService.resolve_for_products(
        discount_session,
        products=[custom, disabled, low_margin],
        effective_prices={
            int(custom.id): 2_200,
            int(disabled.id): 2_200,
            int(low_margin.id): 1_800,
        },
        supply_metrics={
            int(custom.id): {"min_cost_byn": 1_600},
            int(disabled.id): {"min_cost_byn": 1_600},
            int(low_margin.id): {"min_cost_byn": 1_600},
        },
    )

    assert decisions[int(custom.id)].applied_discount == 300
    assert decisions[int(custom.id)].source == "product_override"
    assert (
        decisions[int(disabled.id)].status == ManagerInstallationDiscountStatus.disabled
    )
    assert decisions[int(disabled.id)].applied_discount == 0
    assert (
        decisions[int(low_margin.id)].status
        == ManagerInstallationDiscountStatus.blocked_low_margin
    )
    assert decisions[int(low_margin.id)].applied_discount == 0


@pytest.mark.asyncio
async def test_effective_storefront_price_is_used_instead_of_canonical_price(
    discount_session,
):
    product = (await _products(discount_session, 1))[0]
    product.price = 3_000
    discount_session.add(
        InstallationDiscountPolicy(
            id=1,
            is_enabled=True,
            default_discount=100,
            minimum_margin=350,
        )
    )
    await discount_session.commit()

    decision = (
        await InstallationDiscountService.resolve_for_products(
            discount_session,
            products=[product],
            effective_prices={int(product.id): 1_800},
            supply_metrics={int(product.id): {"min_cost_byn": 1_600}},
        )
    )[int(product.id)]

    assert decision.effective_price == 1_800
    assert decision.margin == 200
    assert decision.status == ManagerInstallationDiscountStatus.blocked_low_margin
    assert decision.applied_discount == 0
