from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, sessionmaker
from sqlmodel import SQLModel, select

import scripts.normalize_legacy as normalize_legacy
import services.importer_service as importer_module
from models import Product, Tag, TagGroup
from schemas import ProductUpdate
from services.product_write_service import ProductWriteService
from services.product_manager_service import ProductManagerService


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'catalog_category.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_tags(session: AsyncSession) -> tuple[Tag, Tag, Tag]:
    category = TagGroup(title="Категория", slug="category", allow_multiple=False)
    feature = TagGroup(title="Feature", slug="feature", allow_multiple=True)
    session.add_all([category, feature])
    await session.flush()
    industrial = Tag(title="Полупромышленные", slug="cat-industrial", group_id=category.id)
    household = Tag(title="Бытовые", slug="cat-household", group_id=category.id)
    preserved = Tag(title="Wi-Fi", slug="wifi-builtin", group_id=feature.id)
    session.add_all([industrial, household, preserved])
    await session.commit()
    return industrial, household, preserved


async def _category_slugs(session: AsyncSession, product_id: int) -> set[str]:
    session.expire_all()
    row = await session.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.tags).selectinload(Tag.group))
    )
    return {
        tag.slug
        for tag in row.scalar_one().tags
        if tag.group is not None and tag.group.slug == "category"
    }


@pytest.mark.asyncio
async def test_manager_override_replaces_stale_category_and_preserves_other_tags_and_price(sqlite_session):
    industrial, _household, preserved = await _seed_tags(sqlite_session)
    malformed = Tag(
        title="Malformed multi",
        slug="cat-multi",
        group_id=preserved.group_id,
    )
    sqlite_session.add(malformed)
    await sqlite_session.commit()
    product = Product(
        title="TCL series 276 industrial legacy title",
        slug="tcl-276",
        price=3210,
        product_kind="complete_split_system",
        specs={"type": "сплит-система", "indoor_type": "кассетный"},
        tags=[industrial, malformed, preserved],
    )
    sqlite_session.add(product)
    await sqlite_session.commit()

    await ProductWriteService.update_product(
        sqlite_session,
        product.id,
        update_data={
            "title": product.title,
            "price": product.price,
            "product_kind": "complete_split_system",
            "specs": {"type": "сплит-система", "indoor_type": "консольный"},
            "catalog_category_override": "cat-household",
        },
        tag_ids=[industrial.id, malformed.id, preserved.id],
    )

    refreshed = await sqlite_session.get(Product, product.id)
    assert refreshed.catalog_category_override == "cat-household"
    assert refreshed.price == 3210
    assert await _category_slugs(sqlite_session, product.id) == {"cat-household"}
    all_tags = await sqlite_session.execute(
        select(Tag.slug).join(Tag.products).where(Product.id == product.id)
    )
    all_slugs = set(all_tags.scalars())
    # Brand synchronization may add the canonical TCL tag, but no stale
    # canonical category survives and the unrelated Wi-Fi tag remains.
    assert all_slugs == {"cat-household", "tcl", "wifi-builtin"}
    manager_payload = await ProductManagerService.get_manager_product(sqlite_session, product.id)
    assert manager_payload["catalog_category_override"] == "cat-household"
    assert manager_payload["catalog_category"] == "cat-household"


@pytest.mark.asyncio
async def test_price_only_legacy_patch_does_not_reclassify_automatic_product(sqlite_session):
    industrial, _household, _preserved = await _seed_tags(sqlite_session)
    product = Product(
        title="TCL industrial legacy title",
        slug="tcl-price-only",
        price=1000,
        product_kind="complete_split_system",
        specs={
            "Тип": "сплит-система",
            "Тип внутреннего блока": "консольный",
            "wifi": "ready",
            "hidden_legacy_value": "keep",
        },
        tags=[industrial],
    )
    sqlite_session.add(product)
    await sqlite_session.commit()
    product_id = product.id

    await ProductWriteService.update_product(
        sqlite_session,
        product_id,
        update_data={"price": 1100},
    )

    assert await _category_slugs(sqlite_session, product_id) == {"cat-industrial"}


@pytest.mark.asyncio
async def test_full_save_ignores_non_category_spec_changes(sqlite_session):
    industrial, _household, _preserved = await _seed_tags(sqlite_session)
    product = Product(
        title="TCL legacy title",
        slug="tcl-full-save",
        price=1000,
        product_kind="complete_split_system",
        specs={
            "type": "сплит-система",
            "indoor_type": "консольный",
            "wifi": "ready",
            "hidden_legacy_value": "keep",
        },
        tags=[industrial],
    )
    sqlite_session.add(product)
    await sqlite_session.commit()

    await ProductWriteService.update_product(
        sqlite_session,
        product.id,
        update_data={
            "title": "TCL legacy title",
            "price": 1100,
            "product_kind": "complete_split_system",
            "specs": {
                "type": "сплит-система",
                "indoor_type": "консольный",
                "wifi": False,
                "multi_compat_mode": "standalone",
            },
        },
        tag_ids=[industrial.id],
    )

    assert await _category_slugs(sqlite_session, product.id) == {"cat-industrial"}


@pytest.mark.asyncio
async def test_type_change_reclassifies_automatic_product(sqlite_session):
    industrial, _household, _preserved = await _seed_tags(sqlite_session)
    product = Product(
        title="TCL Model",
        slug="tcl-type-change",
        price=1000,
        product_kind="complete_split_system",
        specs={"type": "полупромышленный", "indoor_type": "кассетный"},
        tags=[industrial],
    )
    sqlite_session.add(product)
    await sqlite_session.commit()

    await ProductWriteService.update_product(
        sqlite_session,
        product.id,
        update_data={
            "specs": {"type": "сплит-система", "indoor_type": "консольный"},
        },
    )

    assert await _category_slugs(sqlite_session, product.id) == {"cat-household"}


@pytest.mark.asyncio
async def test_create_makes_missing_category_tag(sqlite_session):
    result = await ProductWriteService.create_product(
        sqlite_session,
        {
            "title": "Standalone console",
            "price": 900,
            "specs": {"type": "сплит-система", "indoor_type": "консольный"},
        },
    )

    assert await _category_slugs(sqlite_session, result["id"]) == {"cat-household"}


@pytest.mark.asyncio
async def test_override_reset_rederives_category_and_duplicate_preserves_or_resets_it(sqlite_session):
    industrial, _household, _preserved = await _seed_tags(sqlite_session)
    product = Product(
        title="TCL industrial old title",
        slug="tcl-reset",
        price=2000,
        product_kind="complete_split_system",
        catalog_category_override="cat-household",
        specs={"type": "сплит-система", "indoor_type": "консольный"},
        tags=[industrial],
    )
    sqlite_session.add(product)
    await sqlite_session.commit()
    product_id = product.id

    copied = await ProductWriteService.duplicate_product(
        sqlite_session, product_id, overrides={}, copy_tags=True
    )
    preserved_copy = await sqlite_session.get(Product, copied["id"])
    assert preserved_copy.catalog_category_override == "cat-household"
    assert await _category_slugs(sqlite_session, preserved_copy.id) == {"cat-household"}

    reset_copy = await ProductWriteService.duplicate_product(
        sqlite_session,
        product_id,
        overrides={"catalog_category_override": None},
        copy_tags=True,
    )
    auto_copy = await sqlite_session.get(Product, reset_copy["id"])
    assert auto_copy.catalog_category_override is None
    assert await _category_slugs(sqlite_session, auto_copy.id) == {"cat-household"}

    await ProductWriteService.update_product(
        sqlite_session,
        product_id,
        update_data={"catalog_category_override": None},
    )
    reset = await sqlite_session.get(Product, product_id)
    assert reset.catalog_category_override is None
    assert await _category_slugs(sqlite_session, product_id) == {"cat-household"}


@pytest.mark.asyncio
async def test_normalization_and_import_keep_override_and_replace_conflicting_category_tags(
    sqlite_session,
    monkeypatch: pytest.MonkeyPatch,
):
    industrial, _household, preserved = await _seed_tags(sqlite_session)
    product = Product(
        title="Source industrial legacy title",
        slug="source-override",
        price=1750,
        catalog_category_override="cat-household",
        specs={"type": "сплит-система", "indoor_type": "кассетный"},
        source_url="https://source.test/item",
        tags=[industrial, preserved],
    )
    sqlite_session.add(product)
    await sqlite_session.commit()

    database_url = str(sqlite_session.bind.url)
    monkeypatch.setattr(normalize_legacy.settings, "DATABASE_URL", database_url)
    await normalize_legacy.run_normalize()
    assert await _category_slugs(sqlite_session, product.id) == {"cat-household"}
    normalized = await sqlite_session.get(Product, product.id)
    assert normalized.price == 1750
    assert normalized.catalog_category_override == "cat-household"

    factory = sessionmaker(bind=sqlite_session.bind, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(importer_module, "async_session_maker", factory)

    class Parser:
        def supports(self, _url: str) -> bool:
            return True

        async def parse(self, url: str) -> dict:
            return {
                "source_url": url,
                "title": "Source industrial legacy title",
                "slug": "source-override",
                "description": "reimported",
                "price": 1750,
                "metrics": {},
                "specs": {"type": "сплит-система", "indoor_type": "кассетный"},
                "categories": [],
            }

    importer = importer_module.ImporterService()
    importer.parsers = [Parser()]
    await importer.import_product("https://source.test/item", update_existing=True)

    assert await _category_slugs(sqlite_session, product.id) == {"cat-household"}
    reimported = await sqlite_session.get(Product, product.id)
    assert reimported.catalog_category_override == "cat-household"
    assert reimported.price == 1750


@pytest.mark.asyncio
async def test_invalid_override_is_422_in_schema_bound_api():
    app = FastAPI()

    @app.patch("/product")
    async def update_product(payload: ProductUpdate):
        return payload.model_dump(exclude_unset=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/product", json={"catalog_category_override": "cat-invalid"})

    assert response.status_code == 422
