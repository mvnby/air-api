from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import (
    GlobalConfig,
    InstallationRate,
    Order,
    OrderProductLink,
    OrderServiceLink,
    Product,
    Service,
    Storefront,
    Tag,
    Tenant,
)
from schemas import OrderPayload
from services.installation_pricing_service import (
    InstallationPricingError,
    InstallationPricingService,
)
from services.website_order_service import WebsiteOrderService


@pytest.fixture
async def sqlite_checkout_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'checkout-pricing.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            Tenant(
                id=1,
                slug="mvn",
                display_name="MVN",
                kind="operator",
                status="active",
                is_system=True,
            )
        )
        await session.flush()
        session.add(
            Storefront(
                id=1,
                tenant_id=1,
                slug="main",
                display_name="MVN",
                status="active",
                currency="BYN",
                is_default=True,
            )
        )
        await session.commit()
        yield session

    await engine.dispose()


async def _seed_checkout_pricing(session: AsyncSession):
    wall = Tag(title="Настенный", slug="wall")
    product = Product(
        title="Canonical Product",
        slug="canonical-product",
        price=2000,
        product_kind="complete_split_system",
        specs={
            "type": "сплит-система",
            "indoor_type": "настенный",
            "capacity_cooling_kw": 5.3,
            "area_m2": 50,
        },
        is_published=True,
    )
    product.tags.append(wall)
    rates = [
        InstallationRate(
            category="Wall",
            power_range="07-12",
            base_price=600,
            extra_pipe_price=50,
            included_pipe_meters=3,
            is_fixed=True,
        ),
        InstallationRate(
            category="Wall",
            power_range="18-24",
            base_price=750,
            extra_pipe_price=65,
            included_pipe_meters=3,
            is_fixed=True,
        ),
        InstallationRate(
            category="Duct",
            power_range="All",
            base_price=1500,
            extra_pipe_price=0,
            included_pipe_meters=3,
            is_fixed=False,
        ),
    ]
    option = Service(
        title="Виброопоры",
        slug="vibration-stand",
        category="installation_option",
        is_active=True,
        base_price=50,
    )
    inactive_option = Service(
        title="Скрытая опция",
        slug="inactive-option",
        category="installation_option",
        is_active=False,
        base_price=10,
    )
    session.add(product)
    session.add_all([*rates, option, inactive_option, GlobalConfig(key="install_discount", value="100")])
    await session.commit()
    await session.refresh(product)
    for rate in rates:
        await session.refresh(rate)
    await session.refresh(option)
    return product, rates, option


def _product_checkout_payload(*, product_id: int, rate_id: int | None, quote_hint: float) -> OrderPayload:
    return OrderPayload.model_validate(
        {
            "customer": {
                "name": "Скрытый клиент",
                "phone": "+375291112233",
                "address": "Минск",
            },
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 2,
                    "with_installation": True,
                    "installation_rate_id": rate_id,
                    "installation_price": quote_hint,
                    "installation_meta": {
                        "source": "checkout",
                        "meters": 5,
                        "type": "Duct",
                        "power_range": "30-36",
                    },
                    "installation_options": ["vibration-stand"],
                }
            ],
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("quote_hint", [-999, 1, 999_999_999])
async def test_public_product_installation_uses_server_rate_discount_and_meters(
    sqlite_checkout_session,
    quote_hint,
    caplog,
    tenant_scope,
):
    product, rates, _option = await _seed_checkout_pricing(sqlite_checkout_session)
    matching_rate = rates[1]
    payload = _product_checkout_payload(
        product_id=int(product.id),
        rate_id=None,
        quote_hint=quote_hint,
    )

    with caplog.at_level("INFO"):
        response = await WebsiteOrderService.create_order(
            sqlite_checkout_session,
            payload,
            tenant_scope=tenant_scope,
            idempotency_key="pricing-checkout-request-0001",
        )

    product_link = (
        await sqlite_checkout_session.execute(
            select(OrderProductLink).where(OrderProductLink.order_id == response.id)
        )
    ).scalar_one()
    service_links = list(
        (
            await sqlite_checkout_session.execute(
                select(OrderServiceLink).where(OrderServiceLink.order_id == response.id)
            )
        ).scalars().all()
    )

    # 750 base + 2 extra meters * 65 - 100 bundle discount + 50 option.
    assert product_link.installation_price == 830
    assert product_link.installation_details["installation_rate_id"] == matching_rate.id
    assert product_link.installation_details["pricing_version"] == "installation-v1"
    assert product_link.installation_details["type"] == "Wall"
    assert product_link.installation_details["power_range"] == "18-24"
    assert product_link.installation_details["pricing_breakdown"] == {
        "currency": "BYN",
        "reason": None,
        "base_price": 750,
        "included_meters": 3,
        "extra_meters": 2.0,
        "extra_meter_unit_price": 65,
        "extra_meters_price": 130,
        "bundle_discount": 100,
        "options": [
            {
                "service_id": _option.id,
                "slug": "vibration-stand",
                "title": "Виброопоры",
                "unit_price": 50,
            }
        ],
        "options_total": 50,
        "total": 830,
    }
    assert sorted(link.price for link in service_links) == [50, 780]
    assert response.total_amount == 5660
    order = await sqlite_checkout_session.get(Order, response.id)
    assert order.tenant_id == tenant_scope.tenant_id
    assert order.storefront_id == tenant_scope.storefront_id
    assert "PUBLIC_INSTALLATION_PRICE_MISMATCH" in caplog.text
    assert "+375291112233" not in caplog.text
    assert "Скрытый клиент" not in caplog.text


@pytest.mark.asyncio
async def test_service_only_installation_uses_selected_server_rate_without_bundle_discount(
    sqlite_checkout_session,
    tenant_scope,
):
    _product, rates, option = await _seed_checkout_pricing(sqlite_checkout_session)
    payload = OrderPayload.model_validate(
        {
            "customer": {"name": "Монтаж", "phone": "+375291112234"},
            "items": [
                {
                    "product_id": None,
                    "quantity": 1,
                    "with_installation": True,
                    "installation_rate_id": rates[0].id,
                    "installation_price": -999,
                    "installation_meta": {"source": "calculator_page", "meters": 4},
                    "installation_options": [option.slug],
                }
            ],
        }
    )

    response = await WebsiteOrderService.create_order(
        sqlite_checkout_session,
        payload,
        tenant_scope=tenant_scope,
        idempotency_key="pricing-checkout-request-0002",
    )
    service_links = list(
        (
            await sqlite_checkout_session.execute(
                select(OrderServiceLink).where(OrderServiceLink.order_id == response.id)
            )
        ).scalars().all()
    )

    assert sorted(link.price for link in service_links) == [50, 650]
    assert response.total_amount == 700
    order = await sqlite_checkout_session.get(Order, response.id)
    assert order.technical_meta["public_installation_pricing"]["pricing_version"] == "installation-v1"
    snapshot = order.technical_meta["public_installation_pricing"]["items"][0]["installation_meta"]
    assert snapshot["pricing_breakdown"]["bundle_discount"] == 0
    assert snapshot["pricing_breakdown"]["total"] == 700


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rate_id", "options", "expected_code"),
    [
        (999_999, [], "installation_rate_not_available"),
        (None, ["unknown-option"], "installation_option_not_available"),
        (None, ["inactive-option"], "installation_option_not_available"),
    ],
)
async def test_public_installation_rejects_unknown_rate_or_option(
    sqlite_checkout_session,
    rate_id,
    options,
    expected_code,
):
    product, rates, _option = await _seed_checkout_pricing(sqlite_checkout_session)
    payload = OrderPayload.model_validate(
        {
            "customer": {"name": "Тест", "phone": "+375291112235"},
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                    "with_installation": True,
                    "installation_rate_id": rate_id,
                    "installation_meta": {"meters": 3},
                    "installation_options": options,
                }
            ],
        }
    )

    with pytest.raises(InstallationPricingError) as exc_info:
        await InstallationPricingService.price_public_items(sqlite_checkout_session, payload.items)

    assert exc_info.value.code == expected_code


@pytest.mark.asyncio
async def test_product_rejects_existing_but_inapplicable_rate(sqlite_checkout_session):
    product, rates, _option = await _seed_checkout_pricing(sqlite_checkout_session)
    payload = _product_checkout_payload(
        product_id=int(product.id),
        rate_id=int(rates[0].id),
        quote_hint=600,
    )

    with pytest.raises(InstallationPricingError) as exc_info:
        await InstallationPricingService.price_public_items(sqlite_checkout_session, payload.items)

    assert exc_info.value.code == "installation_rate_mismatch"


@pytest.mark.asyncio
async def test_non_fixed_service_rate_creates_manual_quote_without_client_price(
    sqlite_checkout_session,
):
    _product, rates, _option = await _seed_checkout_pricing(sqlite_checkout_session)
    payload = OrderPayload.model_validate(
        {
            "customer": {"name": "Клиент", "phone": "+375291112236"},
            "items": [
                {
                    "product_id": None,
                    "quantity": 1,
                    "with_installation": True,
                    "installation_rate_id": rates[2].id,
                    "installation_price": 1_500,
                    "installation_meta": {"meters": 5},
                }
            ],
        }
    )

    priced_items = await InstallationPricingService.price_public_items(
        sqlite_checkout_session,
        payload.items,
    )

    assert priced_items[0]["installation_price"] == 0
    assert priced_items[0]["installation_options"] == []
    assert priced_items[0]["installation_meta"]["pricing_status"] == "manual_quote"
    assert priced_items[0]["installation_meta"]["requires_manager_quote"] is True
    assert (
        priced_items[0]["installation_meta"]["pricing_breakdown"]["reason"]
        == "rate_requires_manual_quote"
    )


def _matching_rate(
    category: str,
    power_range: str = "All",
    *,
    is_fixed: bool = True,
) -> InstallationRate:
    return InstallationRate(
        category=category,
        power_range=power_range,
        base_price=1000,
        extra_pipe_price=50,
        included_pipe_meters=3,
        is_fixed=is_fixed,
    )


@pytest.mark.asyncio
async def test_manual_quote_snapshot_preserves_diagnostic_resolver_reasons(
    sqlite_checkout_session,
):
    duct_tag = Tag(title="Канальный", slug="duct")
    products = [
        Product(
            title="Separate indoor block",
            slug="separate-indoor-block",
            price=1000,
            product_kind="indoor_unit",
            specs={"indoor_type": "канальный"},
            is_published=True,
            tags=[duct_tag],
        ),
        Product(
            title="Missing form factor",
            slug="missing-form-factor",
            price=1000,
            product_kind="complete_split_system",
            specs={"type": "сплит-система", "capacity_cooling_kw": 3.5},
            is_published=True,
        ),
        Product(
            title="Missing capacity",
            slug="missing-capacity",
            price=1000,
            product_kind="complete_split_system",
            specs={"type": "сплит-система", "indoor_type": "настенный", "area_m2": 111},
            is_published=True,
        ),
        Product(
            title="Unsupported column",
            slug="unsupported-column",
            price=1000,
            product_kind="complete_split_system",
            specs={"type": "сплит-система", "indoor_type": "колонный", "capacity_cooling_kw": 7.0},
            is_published=True,
        ),
        Product(
            title="Unknown equipment",
            slug="unknown-equipment",
            price=1000,
            product_kind="unknown",
            specs={},
            is_published=True,
        ),
        Product(
            title="Legacy combined quote",
            slug="legacy-combined-quote",
            price=1000,
            product_kind="complete_split_system",
            specs={"type": "сплит-система", "indoor_type": "кассетный"},
            is_published=True,
        ),
    ]
    sqlite_checkout_session.add_all(
        [
            *products,
            _matching_rate("Wall", "07-12"),
            _matching_rate("Duct"),
            _matching_rate("Cassette/Ceiling", is_fixed=False),
        ]
    )
    await sqlite_checkout_session.commit()
    for product in products:
        await sqlite_checkout_session.refresh(product)

    payload = OrderPayload.model_validate(
        {
            "customer": {"name": "Reasons", "phone": "+375291112237"},
            "items": [
                {
                    "product_id": product.id,
                    "quantity": 1,
                    "with_installation": True,
                    "installation_meta": {"meters": 3},
                }
                for product in products
            ],
        }
    )

    priced_items = await InstallationPricingService.price_public_items(
        sqlite_checkout_session,
        payload.items,
    )

    assert [item["installation_price"] for item in priced_items] == [0, 0, 0, 0, 0, 0]
    assert [
        item["installation_meta"]["pricing_breakdown"]["reason"]
        for item in priced_items
    ] == [
        "ineligible_product_kind",
        "missing_equipment_type",
        "missing_cooling_capacity",
        "no_matching_rate",
        "ineligible_product_kind",
        "rate_requires_manual_quote",
    ]
    assert all(
        item["installation_meta"]["pricing_status"] == "manual_quote"
        for item in priced_items
    )
