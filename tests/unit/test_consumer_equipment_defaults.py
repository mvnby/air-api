from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import Brand, Product, ProductSeries, WarrantyPolicy
from modules.documents.application.consumer_equipment import (
    resolve_consumer_equipment_defaults,
)
from modules.documents.application.context_builder import DocumentContextBuilder
from modules.documents.domain import ConsumerDocumentTerms


@pytest.fixture
async def session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'consumer-defaults.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


def _link(product: Product, *, proposal_id: int, title_snapshot: str | None = None):
    """A loaded order link fixture, without adding unrelated rows to the session."""

    return SimpleNamespace(
        id=None,
        product_id=int(product.id),
        proposal_id=proposal_id,
        title_snapshot=title_snapshot,
        product=product,
    )


@pytest.mark.asyncio
async def test_defaults_use_scoped_product_policy_and_sold_title(session: AsyncSession):
    brand = Brand(title="Midea", slug="midea-consumer-defaults")
    session.add(brand)
    await session.flush()
    series = ProductSeries(
        brand_id=brand.id,
        title="Breezeless",
        slug="breezeless-consumer-defaults",
    )
    session.add(series)
    await session.flush()
    product = Product(
        title="Current catalog title",
        slug="consumer-defaults-midea",
        price=1,
        brand_id=brand.id,
        series_id=series.id,
        specs={"warranty_months": 24},
    )
    session.add(product)
    await session.flush()
    session.add_all(
        [
            WarrantyPolicy(name="Brand", brand_id=brand.id, duration_months=42),
            WarrantyPolicy(name="Series", series_id=series.id, duration_months=48),
            WarrantyPolicy(
                name="Product",
                product_id=product.id,
                duration_months=60,
                terms="По условиям производителя",
            ),
        ]
    )
    await session.flush()

    resolved = await resolve_consumer_equipment_defaults(
        session,
        product_links=[_link(product, proposal_id=1, title_snapshot="Midea MA-09 sold")],
        issue_date=date(2026, 9, 9),
    )

    assert resolved.equipment_brand == "Midea"
    assert resolved.equipment_model == "Current catalog title"
    assert resolved.equipment_serial is None
    assert resolved.goods_warranty_months == 60
    assert resolved.goods_warranty_terms == "По условиям производителя"


@pytest.mark.asyncio
async def test_selected_proposal_controls_the_default_product(session: AsyncSession):
    brand = Brand(title="Gree", slug="gree-consumer-defaults")
    session.add(brand)
    await session.flush()
    selected_product = Product(
        title="Selected product",
        slug="selected-consumer-defaults",
        price=1,
        brand_id=brand.id,
    )
    other_product = Product(title="Other product", slug="other-consumer-defaults", price=1)
    session.add_all([selected_product, other_product])
    await session.flush()
    selected = SimpleNamespace(id=10, is_archived=False, is_selected=True, sort_order=0)
    other = SimpleNamespace(id=11, is_archived=False, is_selected=False, sort_order=1)
    order = SimpleNamespace(
        proposals=[selected, other],
        product_links=[
            _link(selected_product, proposal_id=10, title_snapshot="Sold Gree"),
            _link(other_product, proposal_id=11, title_snapshot="Other sale"),
        ],
        service_links=[],
    )

    _, scoped_links, _ = DocumentContextBuilder._select_proposal_lines(order, None)
    resolved = await resolve_consumer_equipment_defaults(
        session,
        product_links=scoped_links,
        issue_date=date(2026, 9, 9),
    )

    assert resolved.equipment_brand == "Gree"
    assert resolved.equipment_model == "Selected product"
    assert resolved.goods_warranty_months == 36


@pytest.mark.asyncio
async def test_manual_values_and_zero_warranty_are_preserved(session: AsyncSession):
    product = Product(
        title="Catalog model",
        slug="manual-consumer-defaults",
        price=1,
        specs={"warranty_months": 48},
    )
    session.add(product)
    await session.flush()

    resolved = await resolve_consumer_equipment_defaults(
        session,
        product_links=[_link(product, proposal_id=1)],
        terms=ConsumerDocumentTerms(
            equipment_brand="Manual brand",
            equipment_model="Manual model",
            equipment_serial="Manual serial",
            goods_warranty_months=0,
            goods_warranty_terms="Без договорной гарантии",
        ),
        issue_date=date(2026, 9, 9),
    )

    assert resolved.equipment_brand == "Manual brand"
    assert resolved.equipment_model == "Manual model"
    assert resolved.equipment_serial == "Manual serial"
    assert resolved.goods_warranty_months == 0
    assert resolved.goods_warranty_terms == "Без договорной гарантии"


@pytest.mark.asyncio
async def test_ambiguous_or_spec_only_product_falls_back_without_serial(session: AsyncSession):
    first = Product(
        title="First", slug="first-consumer-defaults", price=1, specs={"warranty_months": 48}
    )
    second = Product(title="Second", slug="second-consumer-defaults", price=1)
    session.add_all([first, second])
    await session.flush()

    spec_default = await resolve_consumer_equipment_defaults(
        session,
        product_links=[_link(first, proposal_id=1)],
        issue_date=date(2026, 9, 9),
    )
    ambiguous = await resolve_consumer_equipment_defaults(
        session,
        product_links=[_link(first, proposal_id=1), _link(second, proposal_id=1)],
        issue_date=date(2026, 9, 9),
    )

    assert spec_default.goods_warranty_months == 48
    assert spec_default.equipment_serial is None
    assert ambiguous.equipment_brand is None
    assert ambiguous.equipment_model is None
    assert ambiguous.equipment_serial is None
    assert ambiguous.goods_warranty_months == 36
