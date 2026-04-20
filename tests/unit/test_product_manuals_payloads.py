from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from crud.product import ProductDAO
from models import Product
from services.product_manager_service import ProductManagerService
from services.product_response_mapper import map_product_to_response
from services.product_write_service import ProductWriteService


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    db_path = tmp_path / "product_manuals_payloads.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_manuals_are_serialized_for_public_and_manager_payloads(sqlite_session):
    product = Product(
        title="Haier Flexis Test",
        slug="haier-flexis-manual-test",
        description="desc",
        price=3999,
        area=35,
        is_inverter=True,
        is_published=True,
        specs={"brand": "Haier", "type": "сплит-система"},
    )
    sqlite_session.add(product)
    await sqlite_session.commit()
    await sqlite_session.refresh(product)

    result = await ProductWriteService.update_product(
        sqlite_session,
        product.id,
        update_data={
            "manuals": [
                {
                    "kind": "manual",
                    "title": "Руководство пользователя",
                    "url": "https://haier.example/manual-user.pdf",
                    "source": "manager",
                },
                {
                    "kind": "manual",
                    "title": "Инструкция монтажа",
                    "url": "https://haier.example/manual-install.pdf",
                    "source": "manager",
                },
            ]
        },
        tag_ids=None,
    )
    assert result == {"message": "Product updated", "id": product.id}

    refreshed = await ProductDAO.get_by_id(sqlite_session, product.id)
    assert refreshed is not None
    public_payload = map_product_to_response(refreshed)
    assert len(public_payload.manuals) == 2
    assert {item.title for item in public_payload.manuals} == {
        "Руководство пользователя",
        "Инструкция монтажа",
    }

    manager_payload = await ProductManagerService.get_manager_list(
        sqlite_session,
        page=1,
        limit=20,
        search=None,
        is_published=True,
        area_min=None,
        area_max=None,
        is_inverter=None,
        category_slug=None,
        sort="newest",
    )
    item = next((row for row in manager_payload["items"] if row["id"] == product.id), None)
    assert item is not None
    assert len(item["manuals"]) == 2
