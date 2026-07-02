from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Product, ProductImage, ProductImageVariant
from services.media_storage_service import StoredMediaObject
from services.product_image_processing_contract import (
    ProductImageProcessingStatus,
    ProductImageVariantType,
)
from services.product_legacy_images_backfill_service import ProductLegacyImagesBackfillService


class RecordingStorage:
    provider_name = "r2"

    def __init__(self):
        self.uploads = []

    def build_product_variant_object(
        self,
        *,
        content_hash: str,
        variant_type: str,
        extension: str = "webp",
    ) -> StoredMediaObject:
        path = f"products/variants/{variant_type}/{content_hash}.{extension}"
        return StoredMediaObject(
            url=f"https://cdn.mvn.by/{path}",
            content_hash=content_hash,
            storage_provider=self.provider_name,
            path=path,
        )

    async def save_product_variant(
        self,
        *,
        content: bytes,
        variant_type: str,
        extension: str = "webp",
    ) -> StoredMediaObject:
        import hashlib

        self.uploads.append(
            {
                "content": content,
                "variant_type": variant_type,
                "extension": extension,
            }
        )
        return self.build_product_variant_object(
            content_hash=hashlib.sha256(content).hexdigest(),
            variant_type=variant_type,
            extension=extension,
        )


def _image_bytes(color=(40, 90, 180), *, fmt: str = "WEBP") -> bytes:
    image = Image.new("RGB", (12, 10), color)
    output = BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy_images_backfill.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _make_product(
    session: AsyncSession,
    *,
    product_id: int | None = None,
    images: list[str] | None = None,
    is_published: bool = True,
) -> Product:
    product = Product(
        id=product_id,
        title=f"Legacy images {product_id or ''}".strip(),
        slug=f"legacy-images-{product_id or 'auto'}",
        price=1000,
        area=20,
        specs={},
        images=images or [],
        is_published=is_published,
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


@pytest.mark.asyncio
async def test_legacy_images_backfill_dry_run_plans_unique_local_images_without_db_writes(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    media_path = tmp_path / "media/products/gallery/one.webp"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(_image_bytes())
    product = await _make_product(
        sqlite_session,
        images=[
            "media/products/gallery/one.webp",
            "/media/products/gallery/one.webp",
            "https://example.com/vendor.jpg",
        ],
    )
    storage = RecordingStorage()

    report = await ProductLegacyImagesBackfillService.backfill_to_storage(
        sqlite_session,
        storage=storage,
        execute=False,
        limit=10,
    )

    image = (
        await sqlite_session.execute(
            select(ProductImage).where(ProductImage.product_id == product.id)
        )
    ).scalar_one_or_none()
    assert report["dry_run"] is True
    assert report["inspected_images"] == 2
    assert report["planned_uploads"] == 1
    assert report["skipped_count"] == 1
    assert report["items"][0]["will_create_product_image"] is True
    assert report["skipped"][0]["skip_reason"] == "non_local_url"
    assert image is None
    assert storage.uploads == []


@pytest.mark.asyncio
async def test_legacy_images_backfill_execute_creates_image_and_original_variant(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    media_path = tmp_path / "media/products/gallery/one.webp"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(_image_bytes())
    product = await _make_product(
        sqlite_session,
        images=["media/products/gallery/one.webp"],
    )
    storage = RecordingStorage()

    report = await ProductLegacyImagesBackfillService.backfill_to_storage(
        sqlite_session,
        storage=storage,
        execute=True,
        limit=10,
    )

    image = (
        await sqlite_session.execute(
            select(ProductImage).where(
                ProductImage.product_id == product.id,
                ProductImage.url == "media/products/gallery/one.webp",
            )
        )
    ).scalar_one()
    variant = (
        await sqlite_session.execute(
            select(ProductImageVariant).where(
                ProductImageVariant.product_image_id == image.id,
                ProductImageVariant.variant_type == ProductImageVariantType.ORIGINAL.value,
            )
        )
    ).scalar_one()

    assert report["dry_run"] is False
    assert report["uploaded"] == 1
    assert len(storage.uploads) == 1
    assert variant.storage_provider == "r2"
    assert variant.processing_status == ProductImageProcessingStatus.READY.value
    assert variant.url.startswith("https://cdn.mvn.by/products/variants/original/")


@pytest.mark.asyncio
async def test_legacy_images_backfill_skips_existing_ready_r2_match_with_slash_variant(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    media_path = tmp_path / "media/products/gallery/one.webp"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(_image_bytes())
    product = await _make_product(
        sqlite_session,
        images=["media/products/gallery/one.webp"],
    )
    image = ProductImage(product_id=product.id, url="/media/products/gallery/one.webp")
    sqlite_session.add(image)
    await sqlite_session.flush()
    sqlite_session.add(
        ProductImageVariant(
            product_image_id=image.id,
            variant_type=ProductImageVariantType.ORIGINAL.value,
            url="https://cdn.mvn.by/products/variants/original/existing.webp",
            storage_provider="r2",
            processing_status=ProductImageProcessingStatus.READY.value,
            processing_stage="original_ingest",
        )
    )
    await sqlite_session.commit()
    storage = RecordingStorage()

    report = await ProductLegacyImagesBackfillService.backfill_to_storage(
        sqlite_session,
        storage=storage,
        execute=True,
        limit=10,
    )

    assert report["planned_uploads"] == 0
    assert report["uploaded"] == 0
    assert report["skipped"][0]["skip_reason"] == "already_on_target_provider"
    assert storage.uploads == []
