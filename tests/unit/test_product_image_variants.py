import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Product, ProductImage, ProductImageVariant, ProductSeries
from services.manager_media_service import ManagerMediaService
from services.media_storage_service import LocalProductMediaStorage, StoredMediaObject
from services.product_image_processing_contract import (
    ProductImageProcessingStatus,
    ProductImageVariantType,
)
from services.product_image_processing_provider import (
    CARD_CANVAS_SIZE,
    NoopProductImageProcessor,
    ProductImageProcessingContext,
)
from services.product_image_variant_service import ProductImageVariantService
from scripts.process_product_image_variants import process_product_image_variants


def _image_bytes(color: tuple[int, int, int] = (40, 90, 180), *, fmt: str = "PNG") -> bytes:
    image = Image.new("RGB", (12, 10), color)
    output = BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


def _transparent_product_bytes(*, fmt: str = "PNG") -> bytes:
    image = Image.new("RGBA", (80, 60), (255, 255, 255, 0))
    image.paste((210, 30, 30, 255), box=(18, 12, 62, 48))
    output = BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


class _FakeProductMediaStorage:
    provider_name = "fake_r2"

    def __init__(self):
        self.calls = []

    def build_product_variant_object(
        self,
        *,
        content_hash: str,
        variant_type: str,
        extension: str = "webp",
    ) -> StoredMediaObject:
        return StoredMediaObject(
            url=f"https://cdn.example.test/products/variants/{variant_type}/{content_hash}.{extension}",
            content_hash=content_hash,
            storage_provider=self.provider_name,
            path=f"products/variants/{variant_type}/{content_hash}.{extension}",
        )

    async def save_product_variant(
        self,
        *,
        content: bytes,
        variant_type: str,
        extension: str = "webp",
    ) -> StoredMediaObject:
        self.calls.append(
            {
                "content": content,
                "variant_type": variant_type,
                "extension": extension,
            }
        )
        content_hash = hashlib.sha256(content).hexdigest()
        return self.build_product_variant_object(
            content_hash=content_hash,
            variant_type=variant_type,
            extension=extension,
        )


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


def _write_source_image(tmp_path: Path, name: str, content: bytes | None = None) -> str:
    source_dir = tmp_path / "media/products/shared"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / name
    source_path.write_bytes(content or _image_bytes(fmt="WEBP"))
    return f"/media/products/shared/{name}"


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
async def test_manager_upload_writes_original_variant_through_configured_storage(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    fake_storage = _FakeProductMediaStorage()
    monkeypatch.setattr(
        "services.product_image_variant_service.get_product_media_storage",
        lambda: fake_storage,
    )
    product = await _make_product(sqlite_session)

    result = await ManagerMediaService.save_image_from_bytes(
        image_content=_image_bytes((120, 40, 40)),
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

    assert product.main_image == image.url
    assert image.url.startswith("/media/products/shared/")
    assert original_variant.url.startswith("https://cdn.example.test/products/variants/original/")
    assert original_variant.storage_provider == "fake_r2"
    assert original_variant.content_hash
    assert original_variant.width == 12
    assert original_variant.height == 10
    assert len(fake_storage.calls) == 1
    assert fake_storage.calls[0]["variant_type"] == ProductImageVariantType.ORIGINAL.value
    assert fake_storage.calls[0]["extension"] == "webp"


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
async def test_apply_gallery_to_series_preserves_installation_photos_and_replaces_gallery(
    sqlite_session,
    monkeypatch,
):
    async def _skip_original_variant(*args, **kwargs):
        return None

    monkeypatch.setattr(
        ProductImageVariantService,
        "ensure_original_variant",
        _skip_original_variant,
    )

    series = ProductSeries(title="MDV Smart", slug="mdv-smart")
    sqlite_session.add(series)
    await sqlite_session.flush()

    source = Product(
        title="Source product",
        slug="series-source-product",
        price=1000,
        area=20,
        series_id=series.id,
        main_image="/media/products/shared/source-main.webp",
        specs={},
    )
    target = Product(
        title="Target product",
        slug="series-target-product",
        price=1100,
        area=25,
        series_id=series.id,
        main_image="/media/products/shared/old-main.webp",
        specs={},
    )
    outside = Product(
        title="Outside product",
        slug="outside-product",
        price=1200,
        area=30,
        main_image="/media/products/shared/outside.webp",
        specs={},
    )
    sqlite_session.add_all([source, target, outside])
    await sqlite_session.flush()

    sqlite_session.add_all(
        [
            ProductImage(product_id=source.id, url="/media/products/shared/source-main.webp"),
            ProductImage(product_id=source.id, url="/media/products/shared/source-extra.webp"),
            ProductImage(
                product_id=source.id,
                url="/media/products/shared/source-installation.webp",
                is_installation_photo=True,
            ),
            ProductImage(product_id=target.id, url="/media/products/shared/old-main.webp"),
            ProductImage(product_id=target.id, url="/media/products/shared/old-extra.webp"),
            ProductImage(
                product_id=target.id,
                url="/media/products/shared/target-installation.webp",
                is_installation_photo=True,
            ),
            ProductImage(product_id=outside.id, url="/media/products/shared/outside.webp"),
        ]
    )
    await sqlite_session.flush()

    old_target_image = (
        await sqlite_session.execute(
            select(ProductImage).where(
                ProductImage.product_id == target.id,
                ProductImage.url == "/media/products/shared/old-main.webp",
            )
        )
    ).scalar_one()
    old_target_image_id = old_target_image.id
    sqlite_session.add(
        ProductImageVariant(
            product_image_id=old_target_image_id,
            variant_type=ProductImageVariantType.CARD.value,
            url="/media/products/variants/card/old-main.webp",
            processing_status=ProductImageProcessingStatus.READY.value,
        )
    )
    await sqlite_session.commit()

    preview = await ManagerMediaService.apply_gallery_to_series(
        sqlite_session,
        source.id,
        dry_run=True,
    )

    assert preview["dry_run"] is True
    assert preview["updated_products"] == 1
    assert preview["replaced_links"] == 2
    assert preview["obsolete_urls"] == [
        "/media/products/shared/old-main.webp",
        "/media/products/shared/old-extra.webp",
    ]

    result = await ManagerMediaService.apply_gallery_to_series(sqlite_session, source.id)

    await sqlite_session.refresh(target)
    await sqlite_session.refresh(outside)
    target_images = (
        await sqlite_session.execute(
            select(ProductImage).where(ProductImage.product_id == target.id).order_by(ProductImage.id)
        )
    ).scalars().all()
    outside_images = (
        await sqlite_session.execute(select(ProductImage).where(ProductImage.product_id == outside.id))
    ).scalars().all()
    old_variants = (
        await sqlite_session.execute(
            select(ProductImageVariant).where(ProductImageVariant.product_image_id == old_target_image_id)
        )
    ).scalars().all()

    assert result["updated_products"] == 1
    assert result["images_applied"] == 2
    assert result["replaced_links"] == 2
    assert result["deleted_files_count"] == 0
    assert result["preserved_installation_links"] == 1
    assert target.main_image == source.main_image
    assert [image.url for image in target_images] == [
        "/media/products/shared/target-installation.webp",
        "/media/products/shared/source-main.webp",
        "/media/products/shared/source-extra.webp",
    ]
    assert target.images == [
        "/media/products/shared/source-main.webp",
        "/media/products/shared/source-extra.webp",
    ]
    assert [image.url for image in outside_images] == ["/media/products/shared/outside.webp"]
    assert outside.main_image == "/media/products/shared/outside.webp"
    assert old_variants == []


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
    product.images = [source_url]
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
    assert product.images == [source_url]
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


@pytest.mark.asyncio
async def test_cli_dry_run_scopes_product_and_default_missing_only(sqlite_session):
    first = await _make_product(sqlite_session, 41)
    second = await _make_product(sqlite_session, 42)
    first_image = ProductImage(product_id=first.id, url="/media/products/shared/first.webp")
    second_image = ProductImage(product_id=second.id, url="/media/products/shared/second.webp")
    failed_image = ProductImage(product_id=first.id, url="/media/products/shared/failed.webp")
    sqlite_session.add_all([first_image, second_image, failed_image])
    await sqlite_session.flush()
    sqlite_session.add(
        ProductImageVariant(
            product_image_id=failed_image.id,
            variant_type=ProductImageVariantType.CARD.value,
            processing_status=ProductImageProcessingStatus.FAILED.value,
            processing_stage="variant_generation",
            processing_error="previous failure",
        )
    )
    await sqlite_session.commit()

    report = await process_product_image_variants(
        session=sqlite_session,
        execute=False,
        limit=10,
        product_id=first.id,
        variant_type=ProductImageVariantType.CARD.value,
        provider="noop",
        rembg_model=None,
        include_installation=False,
        only_missing=True,
        retry_failed=False,
    )

    assert report["dry_run"] is True
    assert report["total_candidates"] == 1
    assert report["candidates"][0]["product_image_id"] == first_image.id
    assert report["candidates"][0]["reason"] == "missing_variant"


@pytest.mark.asyncio
async def test_process_missing_variants_respects_bounded_batch(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    product = await _make_product(sqlite_session, 51)
    images = []
    for idx in range(3):
        url = _write_source_image(tmp_path, f"bounded-{idx}.webp")
        images.append(ProductImage(product_id=product.id, url=url))
    sqlite_session.add_all(images)
    await sqlite_session.commit()

    result = await ProductImageVariantService.process_missing_variants(
        sqlite_session,
        variant_type=ProductImageVariantType.CARD.value,
        limit=2,
        dry_run=False,
        provider="noop",
    )

    variant_rows = (
        await sqlite_session.execute(
            select(ProductImageVariant).where(
                ProductImageVariant.variant_type == ProductImageVariantType.CARD.value
            )
        )
    ).scalars().all()
    assert result["processed"] == 2
    assert len(result["variants"]) == 2
    assert len(variant_rows) == 2
    assert {row.processing_status for row in variant_rows} == {
        ProductImageProcessingStatus.READY.value
    }


@pytest.mark.asyncio
async def test_retry_failed_includes_failed_variant_only_when_requested(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    product = await _make_product(sqlite_session, 61)
    source_url = _write_source_image(tmp_path, "retry.webp")
    image = ProductImage(product_id=product.id, url=source_url)
    sqlite_session.add(image)
    await sqlite_session.flush()
    sqlite_session.add(
        ProductImageVariant(
            product_image_id=image.id,
            variant_type=ProductImageVariantType.CARD.value,
            processing_status=ProductImageProcessingStatus.FAILED.value,
            processing_stage="variant_generation",
            processing_error="previous failure",
        )
    )
    await sqlite_session.commit()

    default_report = await ProductImageVariantService.get_missing_variant_candidates(
        sqlite_session,
        variant_type=ProductImageVariantType.CARD.value,
        limit=10,
    )
    retry_report = await ProductImageVariantService.get_missing_variant_candidates(
        sqlite_session,
        variant_type=ProductImageVariantType.CARD.value,
        limit=10,
        retry_failed=True,
    )
    result = await ProductImageVariantService.process_missing_variants(
        sqlite_session,
        variant_type=ProductImageVariantType.CARD.value,
        limit=10,
        dry_run=False,
        provider="noop",
        retry_failed=True,
    )

    assert default_report["total_candidates"] == 0
    assert retry_report["total_candidates"] == 1
    assert retry_report["candidates"][0]["reason"] == "failed_variant"
    assert result["processed"] == 1
    assert result["errors"] == []
    assert result["variants"][0]["processing_status"] == ProductImageProcessingStatus.READY.value


@pytest.mark.asyncio
async def test_idempotent_rerun_does_not_duplicate_ready_variant(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    product = await _make_product(sqlite_session, 71)
    source_url = _write_source_image(tmp_path, "idempotent.webp")
    image = ProductImage(product_id=product.id, url=source_url)
    sqlite_session.add(image)
    await sqlite_session.commit()

    first = await ProductImageVariantService.process_missing_variants(
        sqlite_session,
        variant_type=ProductImageVariantType.CARD.value,
        limit=10,
        dry_run=False,
        provider="noop",
    )
    second = await ProductImageVariantService.process_missing_variants(
        sqlite_session,
        variant_type=ProductImageVariantType.CARD.value,
        limit=10,
        dry_run=False,
        provider="noop",
    )
    variants = (
        await sqlite_session.execute(
            select(ProductImageVariant).where(
                ProductImageVariant.product_image_id == image.id,
                ProductImageVariant.variant_type == ProductImageVariantType.CARD.value,
            )
        )
    ).scalars().all()

    assert first["processed"] == 1
    assert second["processed"] == 0
    assert second["total_candidates"] == 0
    assert len(variants) == 1
    assert variants[0].processing_status == ProductImageProcessingStatus.READY.value


@pytest.mark.asyncio
async def test_batch_error_isolation_records_failed_variant_and_continues(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    product = await _make_product(sqlite_session, 81)
    good_url = _write_source_image(tmp_path, "good.webp")
    good = ProductImage(product_id=product.id, url=good_url)
    missing = ProductImage(product_id=product.id, url="/media/products/shared/missing.webp")
    sqlite_session.add_all([good, missing])
    await sqlite_session.commit()

    result = await ProductImageVariantService.process_missing_variants(
        sqlite_session,
        variant_type=ProductImageVariantType.CARD.value,
        limit=10,
        dry_run=False,
        provider="noop",
    )
    variants = (
        await sqlite_session.execute(
            select(ProductImageVariant).where(
                ProductImageVariant.variant_type == ProductImageVariantType.CARD.value
            )
        )
    ).scalars().all()

    statuses_by_image = {variant.product_image_id: variant.processing_status for variant in variants}
    assert result["processed"] == 1
    assert len(result["errors"]) == 1
    assert statuses_by_image[good.id] == ProductImageProcessingStatus.READY.value
    assert statuses_by_image[missing.id] == ProductImageProcessingStatus.FAILED.value


@pytest.mark.asyncio
async def test_card_canvas_normalization_preserves_alpha_and_expected_dimensions():
    processor = NoopProductImageProcessor()

    result = await processor.process(
        source_content=_transparent_product_bytes(),
        context=ProductImageProcessingContext(
            product_image_id=1,
            source_url="/media/products/shared/source.png",
            variant_type=ProductImageVariantType.CARD.value,
        ),
    )

    with Image.open(BytesIO(result.content)) as output:
        image = output.convert("RGBA")
        bbox = image.getchannel("A").getbbox()

    assert result.width == CARD_CANVAS_SIZE[0]
    assert result.height == CARD_CANVAS_SIZE[1]
    assert image.size == CARD_CANVAS_SIZE
    assert image.getpixel((0, 0))[3] == 0
    assert bbox is not None
    assert bbox[0] >= int(CARD_CANVAS_SIZE[0] * 0.07)
    assert bbox[2] <= int(CARD_CANVAS_SIZE[0] * 0.93) + 1
