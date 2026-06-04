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
from services.product_media_migration_service import ProductMediaMigrationService


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


async def _sqlite_session(tmp_path: Path):
    db_path = tmp_path / "media_migration.db"
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


async def _make_product_with_media(
    session: AsyncSession,
    tmp_path: Path,
) -> tuple[Product, ProductImage, ProductImageVariant]:
    product = Product(
        title="Migration product",
        slug="migration-product",
        price=1000,
        area=20,
        specs={},
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)

    shared_dir = tmp_path / "media/products/shared"
    variant_dir = tmp_path / "media/products/variants/card"
    shared_dir.mkdir(parents=True, exist_ok=True)
    variant_dir.mkdir(parents=True, exist_ok=True)
    original_path = shared_dir / "original.webp"
    card_path = variant_dir / "card.webp"
    original_path.write_bytes(_image_bytes())
    card_path.write_bytes(_image_bytes((80, 20, 20)))

    original_url = "/media/products/shared/original.webp"
    card_url = "/media/products/variants/card/card.webp"
    product.main_image = original_url
    product.images = [original_url]
    image = ProductImage(product_id=product.id, url=original_url)
    session.add(image)
    await session.flush()
    variant = ProductImageVariant(
        product_image_id=image.id,
        variant_type=ProductImageVariantType.CARD.value,
        url=card_url,
        storage_provider="local",
        processing_status=ProductImageProcessingStatus.READY.value,
        processing_stage="storage_save",
    )
    session.add(variant)
    await session.commit()
    await session.refresh(product)
    await session.refresh(image)
    await session.refresh(variant)
    return product, image, variant


@pytest.mark.asyncio
async def test_media_migration_dry_run_plans_uploads_without_db_writes(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    product, image, variant = await _make_product_with_media(sqlite_session, tmp_path)
    storage = RecordingStorage()

    report = await ProductMediaMigrationService.migrate_to_storage(
        sqlite_session,
        storage=storage,
        execute=False,
        limit=10,
    )
    original_variant = (
        await sqlite_session.execute(
            select(ProductImageVariant).where(
                ProductImageVariant.product_image_id == image.id,
                ProductImageVariant.variant_type == ProductImageVariantType.ORIGINAL.value,
            )
        )
    ).scalar_one_or_none()
    await sqlite_session.refresh(variant)
    await sqlite_session.refresh(product)

    assert report["dry_run"] is True
    assert report["planned_uploads"] == 2
    assert {item["variant_type"] for item in report["items"]} == {"original", "card"}
    assert storage.uploads == []
    assert original_variant is None
    assert variant.url == "/media/products/variants/card/card.webp"
    assert product.main_image == image.url
    assert product.images == [image.url]


@pytest.mark.asyncio
async def test_media_migration_execute_updates_variants_but_preserves_product_urls(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    product, image, variant = await _make_product_with_media(sqlite_session, tmp_path)
    storage = RecordingStorage()

    report = await ProductMediaMigrationService.migrate_to_storage(
        sqlite_session,
        storage=storage,
        execute=True,
        limit=10,
    )
    original_variant = (
        await sqlite_session.execute(
            select(ProductImageVariant).where(
                ProductImageVariant.product_image_id == image.id,
                ProductImageVariant.variant_type == ProductImageVariantType.ORIGINAL.value,
            )
        )
    ).scalar_one()
    await sqlite_session.refresh(variant)
    await sqlite_session.refresh(product)
    await sqlite_session.refresh(image)

    assert report["dry_run"] is False
    assert report["uploaded"] == 2
    assert len(storage.uploads) == 2
    assert original_variant.storage_provider == "r2"
    assert original_variant.url.startswith("https://cdn.mvn.by/products/variants/original/")
    assert variant.storage_provider == "r2"
    assert variant.url.startswith("https://cdn.mvn.by/products/variants/card/")
    assert product.main_image == "/media/products/shared/original.webp"
    assert product.images == ["/media/products/shared/original.webp"]
    assert image.url == "/media/products/shared/original.webp"
