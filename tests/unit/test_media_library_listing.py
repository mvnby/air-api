from datetime import datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import models  # noqa: F401
from models import (
    Article,
    Brand,
    MediaAsset,
    Product,
    ProductAttachment,
    ProductImage,
    ProductImageVariant,
    ProductSeries,
    Service,
)
from services.media_library_service import MediaLibraryService


@pytest.fixture()
async def sqlite_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
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


async def _capture_selects(session: AsyncSession, callback):
    statements: list[str] = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(session.bind.sync_engine, "before_cursor_execute", capture)
    try:
        result = await callback()
    finally:
        event.remove(session.bind.sync_engine, "before_cursor_execute", capture)
    return result, statements


@pytest.mark.asyncio
async def test_list_assets_filters_counts_and_paginates_in_sql(
    sqlite_session: AsyncSession,
):
    now = datetime.now()
    sqlite_session.add_all(
        [
            MediaAsset(
                title=f"Needle {index:03d}",
                kind="product",
                tags=["target"],
                processing_status="ready",
                url=f"/media/target-{index}.webp",
                created_at=now + timedelta(seconds=index),
            )
            for index in range(105)
        ]
        + [
            MediaAsset(
                title=f"Needle distractor {index:03d}",
                kind="product",
                tags=["other"],
                processing_status="ready",
                url=f"/media/distractor-{index}.webp",
                created_at=now + timedelta(minutes=10, seconds=index),
            )
            for index in range(30)
        ]
    )
    await sqlite_session.commit()

    listing, statements = await _capture_selects(
        sqlite_session,
        lambda: MediaLibraryService.list_assets(
            session=sqlite_session,
            page=2,
            limit=500,
            query="Needle",
            kind="product",
            tag="  target  ",
            status="ready",
        ),
    )

    assert listing["meta"] == {
        "total": 105,
        "page": 2,
        "limit": 100,
        "pages": 2,
    }
    assert len(listing["items"]) == 5
    assert all(item["tags"] == ["target"] for item in listing["items"])
    assert len(statements) == 4
    assert "json_each(media_asset.tags)" in statements[0]
    assert " LIMIT ? OFFSET ?" in statements[1]


@pytest.mark.asyncio
async def test_list_assets_query_count_does_not_grow_with_page_size(
    sqlite_session: AsyncSession,
):
    now = datetime.now()
    sqlite_session.add_all(
        [
            MediaAsset(
                title=f"Asset {index}",
                url=f"/media/asset-{index}.webp",
                created_at=now + timedelta(seconds=index),
            )
            for index in range(40)
        ]
    )
    await sqlite_session.commit()

    one_item, one_item_statements = await _capture_selects(
        sqlite_session,
        lambda: MediaLibraryService.list_assets(
            session=sqlite_session,
            page=1,
            limit=1,
        ),
    )
    forty_items, forty_item_statements = await _capture_selects(
        sqlite_session,
        lambda: MediaLibraryService.list_assets(
            session=sqlite_session,
            page=1,
            limit=40,
        ),
    )

    assert len(one_item["items"]) == 1
    assert len(forty_items["items"]) == 40
    assert len(one_item_statements) == 4
    assert len(forty_item_statements) == 4


@pytest.mark.asyncio
async def test_batched_usage_count_matches_existing_usage_semantics(
    sqlite_session: AsyncSession,
):
    shared_url = "/media/shared.webp"
    product = Product(
        title="Shared product",
        slug="shared-product",
        price=100,
        main_image=shared_url,
    )
    sqlite_session.add(product)
    await sqlite_session.flush()
    image = ProductImage(product_id=int(product.id), url=shared_url)
    sqlite_session.add(image)
    await sqlite_session.flush()
    sqlite_session.add_all(
        [
            ProductImageVariant(
                product_image_id=int(image.id),
                variant_type="card",
                url=shared_url,
            ),
            ProductAttachment(
                product_id=int(product.id),
                kind="manual",
                title="Manual",
                url=shared_url,
            ),
            Article(
                title="Shared article",
                slug="shared-article",
                content="content",
                main_image=shared_url,
                cover_image=shared_url,
            ),
            Brand(title="Shared brand", slug="shared-brand", logo_url=shared_url),
            ProductSeries(
                title="Shared series",
                slug="shared-series",
                hero_image=shared_url,
                gallery_images=[shared_url, shared_url],
                feature_blocks=[
                    {"title": "One", "image_url": shared_url},
                    {"title": "Two", "image_url": shared_url},
                ],
            ),
            Service(title="Shared service", slug="shared-service", image=shared_url),
            MediaAsset(title="Shared asset", url=shared_url),
        ]
    )
    await sqlite_session.commit()

    listing = await MediaLibraryService.list_assets(session=sqlite_session)
    existing_count = await MediaLibraryService._usage_count(sqlite_session, shared_url)

    assert existing_count == 12
    assert listing["items"][0]["usage_count"] == existing_count
