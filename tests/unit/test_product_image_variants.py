from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Product, ProductImage, ProductImageVariant
from services.manager_media_service import ManagerMediaService
from services.media_storage_service import LocalProductMediaStorage
from services.product_image_processing_contract import (
    ProductImageProcessingStatus,
    ProductImageVariantType,
)
from services.product_image_processing_provider import NoopProductImageProcessor
from services.product_image_variant_service import ProductImageVariantService


def _image_bytes(color: tuple[int, int, int] = (40, 90, 180), *, fmt: str = "PNG") -> bytes:
    image = Image.new("RGB", (12, 10), color)
    output = BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


async def _sqlite_session(tmp_path: Path):
    db_path = tmp_path / "image_variants.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    async for session in _sqlite_session(tmp_path):
        yield session


async def _make_product(session: AsyncSession, idx: int = 1) -> Product:
    product = Product(
        title=f"Variant product {idx}",
        slug=f"variant-product-{idx}",
        price=1000 + idx,
        area=20,
        specs={},
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


@pytest.mark.asyncio
async def test_local_storage_and_noop_provider_store_variant_copy(tmp_path: Path):
    storage = LocalProductMediaStorage(base_dir=tmp_path / "media/products/variants")
    processor = NoopProductImageProcessor()

    processed = await processor.process(
        source_content=_image_bytes(fmt="WEBP"),
        context=None,  # type: ignore[arg-type]
    )
    stored = await storage.save_product_variant(
        content=processed.content,
        variant_type=ProductImageVariantType.CARD.value,
        extension=processed.extension,
    )

    assert stored.storage_provider == "local"
    assert stored.url.startswith("/")
    assert stored.url.endswith(".webp")
    assert Path(stored.path).exists()


@pytest.mark.asyncio
async def test_manager_upload_preserves_current_url_and_creates_original_variant(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    product = await _make_product(sqlite_session)

    result = await ManagerMediaService.save_image_from_bytes(
        image_content=_image_bytes(),
        product_id=product.id,
        session=sqlite_session,
        set_main=True,
        is_installation=False,
    )

    await sqlite_session.refresh(product)
    image = (
        await sqlite_session.execute(select(ProductImage).where(ProductImage.id == result["id"]))
    ).scalar_one()
    original_variant = (
        await sqlite_session.execute(
            select(ProductImageVariant).where(
                ProductImageVariant.product_image_id == image.id,
                ProductImageVariant.variant_type == ProductImageVariantType.ORIGINAL.value,
            )
        )
    ).scalar_one()

    assert result["url"] == image.url
    assert product.main_image == image.url
    assert product.images == [image.url]
    assert original_variant.url == image.url
    assert original_variant.processing_status == ProductImageProcessingStatus.READY.value
    assert Path(image.url.lstrip("/")).exists()


@pytest.mark.asyncio
async def test_delete_shared_image_keeps_file_until_last_image_and_variant_reference(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    first = await _make_product(sqlite_session, 31)
    second = await _make_product(sqlite_session, 32)
    shared_url = "/media/products/shared/delete-safe.webp"
    shared_path = tmp_path / shared_url.lstrip("/")
    shared_path.parent.mkdir(parents=True, exist_ok=True)
    shared_path.write_bytes(_image_bytes(fmt="WEBP"))

    first_image = ProductImage(product_id=first.id, url=shared_url)
    second_image = ProductImage(product_id=second.id, url=shared_url)
    sqlite_session.add_all([first_image, second_image])
    await sqlite_session.flush()
    await ProductImageVariantService.ensure_original_variant(sqlite_session, first_image)
    await ProductImageVariantService.ensure_original_variant(sqlite_session, second_image)
    await sqlite_session.commit()
    await sqlite_session.refresh(first_image)
    await sqlite_session.refresh(second_image)

    await ManagerMediaService.delete_gallery_image(sqlite_session, first_image.id)
    assert shared_path.exists()

    await ManagerMediaService.delete_gallery_image(sqlite_session, second_image.id)
    assert not shared_path.exists()


@pytest.mark.asyncio
async def test_variant_dry_run_excludes_installation_and_ready_variants(sqlite_session):
    product = await _make_product(sqlite_session)
    gallery = ProductImage(product_id=product.id, url="/media/products/shared/gallery.webp")
    installation = ProductImage(
        product_id=product.id,
        url="/media/products/shared/install.webp",
        is_installation_photo=True,
    )
    ready = ProductImage(product_id=product.id, url="/media/products/shared/ready.webp")
    sqlite_session.add_all([gallery, installation, ready])
    await sqlite_session.flush()
    sqlite_session.add(
        ProductImageVariant(
            product_image_id=ready.id,
            variant_type=ProductImageVariantType.CARD.value,
            url="/media/products/variants/card/ready.webp",
            processing_status=ProductImageProcessingStatus.READY.value,
            processing_stage="storage_save",
        )
    )
    await sqlite_session.commit()

    report = await ProductImageVariantService.get_missing_variant_candidates(
        sqlite_session,
        variant_type=ProductImageVariantType.CARD.value,
        limit=20,
    )

    assert report["total_candidates"] == 1
    assert report["candidates"][0]["product_image_id"] == gallery.id


@pytest.mark.asyncio
async def test_reprocess_skips_installation_catalog_variant(sqlite_session):
    product = await _make_product(sqlite_session)
    image = ProductImage(
        product_id=product.id,
        url="/media/products/shared/install.webp",
        is_installation_photo=True,
    )
    sqlite_session.add(image)
    await sqlite_session.commit()
    await sqlite_session.refresh(image)

    result = await ProductImageVariantService.reprocess_variant(
        sqlite_session,
        product_image_id=image.id,
        variant_type=ProductImageVariantType.CARD.value,
    )

    assert result["processing_status"] == ProductImageProcessingStatus.SKIPPED.value
    assert "Installation photos" in result["processing_error"]


@pytest.mark.asyncio
async def test_reprocess_local_image_creates_card_variant_without_mutating_current_fields(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    product = await _make_product(sqlite_session)
    source_dir = tmp_path / "media/products/shared"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source.webp"
    source_path.write_bytes(_image_bytes(fmt="WEBP"))
    source_url = "/media/products/shared/source.webp"
    product.main_image = source_url
    image = ProductImage(product_id=product.id, url=source_url)
    sqlite_session.add(image)
    await sqlite_session.commit()
    await sqlite_session.refresh(image)

    result = await ProductImageVariantService.reprocess_variant(
        sqlite_session,
        product_image_id=image.id,
        variant_type=ProductImageVariantType.CARD.value,
    )
    await sqlite_session.refresh(product)
    await sqlite_session.refresh(image)

    assert result["processing_status"] == ProductImageProcessingStatus.READY.value
    assert result["url"].startswith("/media/products/variants/card/")
    assert result["url"] != image.url
    assert Path(result["url"].lstrip("/")).exists()
    assert product.main_image == source_url
    assert image.url == source_url


@pytest.mark.asyncio
async def test_reprocess_failed_source_records_error_without_mutating_originals(
    sqlite_session,
):
    product = await _make_product(sqlite_session)
    product.main_image = "https://example.com/current.jpg"
    image = ProductImage(product_id=product.id, url="https://example.com/source.jpg")
    sqlite_session.add(image)
    await sqlite_session.commit()
    await sqlite_session.refresh(image)

    result = await ProductImageVariantService.reprocess_variant(
        sqlite_session,
        product_image_id=image.id,
        variant_type=ProductImageVariantType.CARD.value,
    )
    await sqlite_session.refresh(product)
    await sqlite_session.refresh(image)

    assert result["processing_status"] == ProductImageProcessingStatus.FAILED.value
    assert result["processing_error"] == "Source image is not available in local media storage"
    assert product.main_image == "https://example.com/current.jpg"
    assert image.url == "https://example.com/source.jpg"
