from datetime import datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from models import MediaAsset, Product, ProductSeries
from services.media_library_service import MediaLibraryService


@pytest.mark.asyncio
async def test_postgres_media_listing_uses_bounded_batch_queries(db_engine):
    assert db_engine.dialect.name == "postgresql"
    session_factory = sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        now = datetime.now()
        session.add_all(
            [
                MediaAsset(
                    title=f"Target asset {index:02d}",
                    kind="product",
                    tags=["featured"],
                    processing_status="ready",
                    url=f"/media/target-{index}.webp",
                    created_at=now + timedelta(seconds=index),
                )
                for index in range(40)
            ]
            + [
                MediaAsset(
                    title=f"Distractor {index:02d}",
                    kind="product",
                    tags=["other"],
                    processing_status="ready",
                    url=f"/media/distractor-{index}.webp",
                    created_at=now + timedelta(minutes=10, seconds=index),
                )
                for index in range(10)
            ]
        )
        referenced_url = "/media/target-39.webp"
        session.add(
            Product(
                title="Referenced product",
                slug="referenced-product",
                price=100,
                main_image=referenced_url,
            )
        )
        session.add(
            ProductSeries(
                title="Referenced series",
                slug="referenced-series",
                gallery_images=[referenced_url],
                feature_blocks=[{"title": "Feature", "image_url": referenced_url}],
            )
        )
        await session.commit()

        statements: list[str] = []

        def capture(connection, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(db_engine.sync_engine, "before_cursor_execute", capture)
        try:
            listing = await MediaLibraryService.list_assets(
                session=session,
                page=1,
                limit=40,
                query="Target asset",
                kind="product",
                tag="featured",
                status="ready",
            )
        finally:
            event.remove(db_engine.sync_engine, "before_cursor_execute", capture)

    assert listing["meta"] == {
        "total": 40,
        "page": 1,
        "limit": 40,
        "pages": 1,
    }
    assert len(listing["items"]) == 40
    assert listing["items"][0]["url"] == referenced_url
    assert listing["items"][0]["usage_count"] == 3
    assert len(statements) == 4
    assert any("CAST(media_asset.tags AS JSONB) @>" in statement for statement in statements)
    assert any("LIMIT" in statement and "OFFSET" in statement for statement in statements)
