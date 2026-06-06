from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Product, ProductImage, ProductMainImageCleanupItem
from services.media_storage_service import LocalProductMediaStorage
from services.product_main_image_cleanup_contract import ProductMainImageCleanupStatus
from services.product_main_image_cleanup_service import ProductMainImageCleanupService


def _image_bytes() -> bytes:
    image = Image.new("RGB", (24, 18), (70, 120, 190))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    db_path = tmp_path / "main_image_cleanup.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _make_product(
    session: AsyncSession,
    idx: int,
    *,
    main_image: str,
) -> Product:
    product = Product(
        title=f"Cleanup product {idx}",
        slug=f"cleanup-product-{idx}",
        price=1000 + idx,
        area=20,
        specs={},
        main_image=main_image,
        images=[main_image],
    )
    session.add(product)
    await session.flush()
    session.add(ProductImage(product_id=product.id, url=main_image))
    await session.commit()
    await session.refresh(product)
    return product


def _write_source(tmp_path: Path, name: str) -> str:
    source_dir = tmp_path / "media/products/shared"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / name).write_bytes(_image_bytes())
    return f"/media/products/shared/{name}"


@pytest.mark.asyncio
async def test_create_batch_generates_candidates_and_records_skip_reasons(
    sqlite_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.chdir(tmp_path)
    good_url = _write_source(tmp_path, "good.png")
    existing_url = _write_source(tmp_path, "existing.png")
    missing_url = "/media/products/shared/missing.png"
    good = await _make_product(sqlite_session, 1, main_image=good_url)
    existing = await _make_product(sqlite_session, 2, main_image=existing_url)
    missing = await _make_product(sqlite_session, 3, main_image=missing_url)

    existing_item = ProductMainImageCleanupItem(
        product_id=existing.id,
        original_image_url=existing_url,
        candidate_image_url="/media/products/variants/main_cleanup/existing.webp",
        approved_image_url="/media/products/variants/main_cleanup/existing.webp",
        status=ProductMainImageCleanupStatus.APPROVED.value,
    )
    sqlite_session.add(existing_item)
    await sqlite_session.commit()

    result = await ProductMainImageCleanupService.create_batch(
        sqlite_session,
        limit=10,
        storage=LocalProductMediaStorage(base_dir=tmp_path / "media/products/variants"),
    )

    assert result["created_count"] == 2
    assert result["candidate_ready_count"] == 1
    assert result["skipped_count"] == 1
    assert result["already_processed_count"] == 1
    by_product = {item["product_id"]: item for item in result["items"]}
    assert by_product[good.id]["status"] == ProductMainImageCleanupStatus.CANDIDATE_READY.value
    assert by_product[good.id]["candidate_image_url"] != good_url
    assert by_product[missing.id]["status"] == ProductMainImageCleanupStatus.SKIPPED.value
    assert by_product[missing.id]["skip_reason"] == "missing_local_source"
    assert result["skipped_existing"][0]["product_id"] == existing.id

    await sqlite_session.refresh(good)
    await sqlite_session.refresh(existing)
    assert good.main_image == good_url
    assert existing.main_image == existing_url


@pytest.mark.asyncio
async def test_approval_updates_main_image_and_preserves_original_metadata(
    sqlite_session: AsyncSession,
):
    original_url = "/media/products/shared/original.png"
    product = await _make_product(sqlite_session, 11, main_image=original_url)
    item = ProductMainImageCleanupItem(
        product_id=product.id,
        source_product_image_id=1,
        original_image_url=original_url,
        candidate_image_url="/media/products/variants/main_cleanup/clean.webp",
        status=ProductMainImageCleanupStatus.CANDIDATE_READY.value,
    )
    sqlite_session.add(item)
    await sqlite_session.commit()
    await sqlite_session.refresh(item)

    result = await ProductMainImageCleanupService.approve_items(
        sqlite_session,
        item_ids=[item.id],
        approved_by="manager",
    )

    assert result["updated_count"] == 1
    await sqlite_session.refresh(product)
    await sqlite_session.refresh(item)
    assert product.main_image == "/media/products/variants/main_cleanup/clean.webp"
    assert product.images == [original_url]
    assert item.original_image_url == original_url
    assert item.approved_image_url == "/media/products/variants/main_cleanup/clean.webp"
    assert item.approved_by == "manager"
    assert item.approved_at is not None


@pytest.mark.asyncio
async def test_rejection_does_not_change_public_main_image(
    sqlite_session: AsyncSession,
):
    original_url = "/media/products/shared/reject-original.png"
    product = await _make_product(sqlite_session, 21, main_image=original_url)
    item = ProductMainImageCleanupItem(
        product_id=product.id,
        original_image_url=original_url,
        candidate_image_url="/media/products/variants/main_cleanup/rejected.webp",
        status=ProductMainImageCleanupStatus.CANDIDATE_READY.value,
    )
    sqlite_session.add(item)
    await sqlite_session.commit()
    await sqlite_session.refresh(item)

    result = await ProductMainImageCleanupService.reject_items(
        sqlite_session,
        item_ids=[item.id],
        reason="bad crop",
    )

    assert result["updated_count"] == 1
    await sqlite_session.refresh(product)
    await sqlite_session.refresh(item)
    assert product.main_image == original_url
    assert item.status == ProductMainImageCleanupStatus.REJECTED.value
    assert item.reject_reason == "bad crop"


@pytest.mark.asyncio
async def test_approval_requires_candidate_ready_status(sqlite_session: AsyncSession):
    product = await _make_product(
        sqlite_session,
        31,
        main_image="/media/products/shared/pending.png",
    )
    item = ProductMainImageCleanupItem(
        product_id=product.id,
        original_image_url=product.main_image,
        candidate_image_url="/media/products/variants/main_cleanup/pending.webp",
        status=ProductMainImageCleanupStatus.PENDING.value,
    )
    sqlite_session.add(item)
    await sqlite_session.commit()
    await sqlite_session.refresh(item)

    result = await ProductMainImageCleanupService.approve_items(
        sqlite_session,
        item_ids=[item.id],
        approved_by="manager",
    )

    assert result["updated_count"] == 0
    assert result["skipped"][0]["reason"] == "candidate_not_ready"
    await sqlite_session.refresh(product)
    assert product.main_image == "/media/products/shared/pending.png"


@pytest.mark.asyncio
async def test_list_items_filters_by_batch_and_status(sqlite_session: AsyncSession):
    first = ProductMainImageCleanupItem(
        batch_id=1,
        product_id=1,
        original_image_url="/media/products/shared/first.png",
        status=ProductMainImageCleanupStatus.CANDIDATE_READY.value,
    )
    second = ProductMainImageCleanupItem(
        batch_id=2,
        product_id=2,
        original_image_url="/media/products/shared/second.png",
        status=ProductMainImageCleanupStatus.REJECTED.value,
    )
    sqlite_session.add_all([first, second])
    await sqlite_session.commit()

    rows = (
        await sqlite_session.execute(select(ProductMainImageCleanupItem))
    ).scalars().all()
    assert len(rows) == 2

    result = await ProductMainImageCleanupService.list_items(
        sqlite_session,
        batch_id=1,
        status=ProductMainImageCleanupStatus.CANDIDATE_READY.value,
    )
    assert [item["product_id"] for item in result["items"]] == [1]
