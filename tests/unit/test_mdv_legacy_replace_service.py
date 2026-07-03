from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import (
    Brand,
    Customer,
    CustomerType,
    Order,
    OrderProductLink,
    OrderStatus,
    Product,
    ProductTagLink,
    Tag,
    TagGroup,
)
from services.mdv_legacy_replace_service import MdvLegacyReplaceService


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mdv_legacy_replace.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_mdv_legacy_replace_preview_splits_deletable_and_order_linked(sqlite_session):
    brand = Brand(title="MDV", slug="mdv")
    group = TagGroup(title="Категория", slug="category")
    sqlite_session.add_all([brand, group])
    await sqlite_session.flush()

    semi_tag = Tag(title="Полупром", slug="cat-industrial", group_id=group.id)
    multi_tag = Tag(title="Мульти", slug="cat-multi", group_id=group.id)
    sqlite_session.add_all([semi_tag, multi_tag])
    await sqlite_session.flush()

    semi = Product(
        title="MDV old cassette",
        slug="mdv-old-cassette",
        price=100,
        area=50,
        brand_id=brand.id,
        specs={"brand": "MDV", "type": "полупромышленный кондиционер"},
    )
    multi = Product(
        title="MDV old multi",
        slug="mdv-old-multi",
        price=100,
        area=20,
        brand_id=brand.id,
        specs={"brand": "MDV", "type": "наружный блок"},
    )
    household = Product(
        title="MDV household",
        slug="mdv-household",
        price=100,
        area=20,
        brand_id=brand.id,
        specs={"brand": "MDV", "type": "сплит-система"},
    )
    sqlite_session.add_all([semi, multi, household])
    await sqlite_session.flush()

    sqlite_session.add_all(
        [
            ProductTagLink(product_id=semi.id, tag_id=semi_tag.id),
            ProductTagLink(product_id=multi.id, tag_id=multi_tag.id),
        ]
    )
    customer = Customer(name="Test", phone="+375291111111", type=CustomerType.individual)
    sqlite_session.add(customer)
    await sqlite_session.flush()
    order = Order(customer_id=customer.id, status=OrderStatus.NEW_LEAD)
    sqlite_session.add(order)
    await sqlite_session.flush()
    sqlite_session.add(OrderProductLink(order_id=order.id, product_id=multi.id, quantity=1, price=100))
    await sqlite_session.commit()

    report = await MdvLegacyReplaceService.preview(
        sqlite_session,
        catalogs=["semi", "multi"],
    )

    assert report["total"] == 2
    assert report["by_catalog"] == {"semi": 1, "multi": 1}
    assert report["deletable_count"] == 1
    assert report["keep_for_update_count"] == 1
    assert {item["slug"] for item in report["samples"]} == {"mdv-old-cassette", "mdv-old-multi"}
