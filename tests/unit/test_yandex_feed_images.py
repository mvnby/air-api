import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageOps
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Product, ProductImage, ProductImageVariant
from services import product_image_processing_provider
from services.media_library_service import MediaLibraryService
from services.media_storage_service import StoredMediaObject
from services.product_image_processing_contract import (
    ProductImageProcessingStatus,
    ProductImageVariantType,
)
from services.product_image_processing_provider import (
    YANDEX_FEED_CANVAS_SIZE,
    NoopProductImageProcessor,
    ProductImageProcessingContext,
)
from services.yandex_feed_image_service import YandexFeedImageService


def _image_bytes(*, fmt: str = "PNG") -> bytes:
    image = Image.new("RGB", (12, 10), (40, 90, 180))
    output = BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


def _resized_image_bytes() -> bytes:
    image = Image.new("RGB", (8, 7), (40, 90, 180))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _transparent_product_bytes() -> bytes:
    image = Image.new("RGBA", (80, 60), (255, 255, 255, 0))
    image.paste((210, 30, 30, 255), box=(18, 12, 62, 48))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _oriented_jpeg_bytes() -> bytes:
    image = Image.new("RGB", (120, 60), (220, 30, 30))
    exif = Image.Exif()
    exif[274] = 6
    output = BytesIO()
    image.save(output, format="JPEG", exif=exif)
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
            url=(
                "https://cdn.example.test/products/variants/"
                f"{variant_type}/{content_hash}.{extension}"
            ),
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
        return self.build_product_variant_object(
            content_hash=hashlib.sha256(content).hexdigest(),
            variant_type=variant_type,
            extension=extension,
        )


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'yandex_feed_images.db'}",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _make_product(session: AsyncSession, idx: int) -> Product:
    product = Product(
        title=f"Yandex feed product {idx}",
        slug=f"yandex-feed-product-{idx}",
        price=1000 + idx,
        specs={"area_m2": 20},
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


def _write_source_image(tmp_path: Path, name: str) -> str:
    source_dir = tmp_path / "media/products/shared"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / name
    source_path.write_bytes(_image_bytes(fmt="WEBP"))
    return f"/media/products/shared/{name}"


@pytest.mark.asyncio
async def test_yandex_feed_converts_webp_to_deterministic_800_jpeg():
    processor = NoopProductImageProcessor()
    context = ProductImageProcessingContext(
        product_image_id=1,
        source_url="/media/products/shared/source.webp",
        variant_type=ProductImageVariantType.YANDEX_FEED.value,
    )

    first = await processor.process(
        source_content=_image_bytes(fmt="WEBP"),
        context=context,
    )
    second = await processor.process(
        source_content=_image_bytes(fmt="WEBP"),
        context=context,
    )

    assert first.extension == "jpg"
    assert first.content == second.content
    with Image.open(BytesIO(first.content)) as output:
        assert output.format == "JPEG"
        assert output.mode == "RGB"
        assert output.size == YANDEX_FEED_CANVAS_SIZE


@pytest.mark.asyncio
async def test_yandex_feed_flattens_transparent_png_on_white_without_cropping():
    processor = NoopProductImageProcessor()

    result = await processor.process(
        source_content=_transparent_product_bytes(),
        context=ProductImageProcessingContext(
            product_image_id=1,
            source_url="/media/products/shared/source.png",
            variant_type=ProductImageVariantType.YANDEX_FEED.value,
        ),
    )

    with Image.open(BytesIO(result.content)) as output:
        image = output.convert("RGB")
        non_white = Image.eval(
            ImageOps.invert(image.convert("L")),
            lambda pixel: 255 if pixel > 20 else 0,
        ).getbbox()

    assert image.size == YANDEX_FEED_CANVAS_SIZE
    assert all(channel >= 245 for channel in image.getpixel((0, 0)))
    assert non_white is not None
    assert non_white[2] - non_white[0] > non_white[3] - non_white[1]


@pytest.mark.asyncio
async def test_yandex_feed_applies_exif_orientation_and_strips_metadata():
    processor = NoopProductImageProcessor()

    result = await processor.process(
        source_content=_oriented_jpeg_bytes(),
        context=ProductImageProcessingContext(
            product_image_id=1,
            source_url="/media/products/shared/oriented.jpg",
            variant_type=ProductImageVariantType.YANDEX_FEED.value,
        ),
    )

    with Image.open(BytesIO(result.content)) as output:
        image = output.convert("RGB")
        non_white = Image.eval(
            ImageOps.invert(image.convert("L")),
            lambda pixel: 255 if pixel > 20 else 0,
        ).getbbox()
        exif = output.getexif()

    assert non_white is not None
    assert non_white[2] - non_white[0] < non_white[3] - non_white[1]
    assert len(exif) == 0


@pytest.mark.asyncio
async def test_yandex_feed_has_a_separate_legacy_source_pixel_limit(monkeypatch):
    monkeypatch.setattr(product_image_processing_provider, "MAX_SOURCE_PIXELS", 100)
    monkeypatch.setattr(
        product_image_processing_provider,
        "MAX_YANDEX_FEED_SOURCE_PIXELS",
        200,
    )
    monkeypatch.setattr(
        product_image_processing_provider,
        "YANDEX_FEED_PREPROCESS_MAX_EDGE",
        8,
    )
    converted_source_sizes = []
    preprocessed_source_sizes = []
    original_convert_to_srgb = product_image_processing_provider._convert_to_srgb

    def preprocess_large_source(source_content):
        with Image.open(BytesIO(source_content)) as image:
            preprocessed_source_sizes.append(image.size)
        return _resized_image_bytes()

    def record_converted_source_size(image):
        converted_source_sizes.append(image.size)
        return original_convert_to_srgb(image)

    monkeypatch.setattr(
        product_image_processing_provider,
        "_preprocess_large_yandex_feed_source",
        preprocess_large_source,
    )
    monkeypatch.setattr(
        product_image_processing_provider,
        "_convert_to_srgb",
        record_converted_source_size,
    )
    source = _image_bytes()
    processor = NoopProductImageProcessor()

    result = await processor.process(
        source_content=source,
        context=ProductImageProcessingContext(
            product_image_id=1,
            source_url="/media/products/shared/legacy-source.png",
            variant_type=ProductImageVariantType.YANDEX_FEED.value,
        ),
    )

    assert result.extension == "jpg"
    assert preprocessed_source_sizes == [(12, 10)]
    assert converted_source_sizes == [(8, 7)]
    with pytest.raises(ValueError, match="too large for safe processing"):
        await processor.process(
            source_content=source,
            context=ProductImageProcessingContext(
                product_image_id=1,
                source_url="/media/products/shared/legacy-source.png",
                variant_type=ProductImageVariantType.CARD.value,
            ),
        )


def test_large_yandex_source_uses_bounded_ffmpeg_preprocess(monkeypatch):
    monkeypatch.setattr(product_image_processing_provider, "MAX_SOURCE_PIXELS", 100)
    monkeypatch.setattr(
        product_image_processing_provider,
        "MAX_YANDEX_FEED_SOURCE_PIXELS",
        200,
    )
    monkeypatch.setattr(
        product_image_processing_provider,
        "YANDEX_FEED_PREPROCESS_MAX_EDGE",
        8,
    )
    monkeypatch.setattr(
        product_image_processing_provider,
        "YANDEX_FEED_PREPROCESS_TIMEOUT_SECONDS",
        5,
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        Path(command[-1]).write_bytes(_resized_image_bytes())
        return product_image_processing_provider.subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        product_image_processing_provider.subprocess,
        "run",
        fake_run,
    )

    output = product_image_processing_provider._preprocess_large_yandex_feed_source(
        _image_bytes()
    )

    with Image.open(BytesIO(output)) as image:
        assert image.size == (8, 7)
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[0] == "ffmpeg"
    assert "-nostdin" in command
    assert "scale=8:8:force_original_aspect_ratio=decrease" in command
    assert kwargs == {
        "check": False,
        "capture_output": True,
        "text": True,
        "timeout": 5,
    }


@pytest.mark.asyncio
async def test_yandex_feed_backfill_is_idempotent(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    product = await _make_product(sqlite_session, 91)
    source_url = _write_source_image(tmp_path, "yandex-feed-source.webp")
    product.main_image = source_url
    image = ProductImage(product_id=product.id, url=source_url)
    sqlite_session.add_all([product, image])
    await sqlite_session.commit()
    storage = _FakeProductMediaStorage()

    first = await YandexFeedImageService.backfill(
        sqlite_session,
        execute=True,
        product_id=product.id,
        storage=storage,
    )
    second = await YandexFeedImageService.backfill(
        sqlite_session,
        execute=True,
        product_id=product.id,
        storage=storage,
    )

    assert first["processed"] == 1
    assert first["errors"] == []
    assert first["processed_items"][0]["url"].endswith(".jpg")
    assert first["processed_items"][0]["width"] == 800
    assert first["processed_items"][0]["height"] == 800
    assert second["processed"] == 0
    assert second["planned"] == 0
    assert second["up_to_date"] == 1
    assert len(storage.calls) == 1


@pytest.mark.asyncio
async def test_yandex_feed_ingests_external_source_without_changing_product_urls(
    sqlite_session,
    monkeypatch,
):
    product = await _make_product(sqlite_session, 97)
    source_url = "https://supplier.example.test/product.png"
    product.main_image = source_url
    image = ProductImage(product_id=product.id, url=source_url)
    sqlite_session.add_all([product, image])
    await sqlite_session.commit()
    source_content = _image_bytes()

    async def download_remote_image(url: str):
        assert url == source_url
        return source_content, "product.png"

    monkeypatch.setattr(
        MediaLibraryService,
        "download_remote_image",
        download_remote_image,
    )
    storage = _FakeProductMediaStorage()

    result = await YandexFeedImageService.backfill(
        sqlite_session,
        execute=True,
        product_id=product.id,
        storage=storage,
    )
    variants = (
        await sqlite_session.execute(
            select(ProductImageVariant)
            .where(ProductImageVariant.product_image_id == image.id)
            .order_by(ProductImageVariant.variant_type)
        )
    ).scalars().all()
    variants_by_type = {variant.variant_type: variant for variant in variants}
    original = variants_by_type[ProductImageVariantType.ORIGINAL.value]
    yandex_feed = variants_by_type[ProductImageVariantType.YANDEX_FEED.value]

    assert result["processed"] == 1
    assert result["errors"] == []
    assert product.main_image == source_url
    assert image.url == source_url
    assert original.url.endswith(".png")
    assert yandex_feed.url.endswith(".jpg")
    assert yandex_feed.source_url == original.url
    assert [call["variant_type"] for call in storage.calls] == [
        ProductImageVariantType.ORIGINAL.value,
        ProductImageVariantType.YANDEX_FEED.value,
    ]


@pytest.mark.asyncio
async def test_yandex_feed_backfill_creates_missing_main_product_image(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    product = await _make_product(sqlite_session, 94)
    product.main_image = _write_source_image(tmp_path, "missing-product-image.webp")
    sqlite_session.add(product)
    await sqlite_session.commit()

    result = await YandexFeedImageService.backfill(
        sqlite_session,
        execute=True,
        product_id=product.id,
        storage=_FakeProductMediaStorage(),
    )
    image = (
        await sqlite_session.execute(
            select(ProductImage).where(ProductImage.product_id == product.id)
        )
    ).scalar_one()
    variant = (
        await sqlite_session.execute(
            select(ProductImageVariant).where(
                ProductImageVariant.product_image_id == image.id,
                ProductImageVariant.variant_type
                == ProductImageVariantType.YANDEX_FEED.value,
            )
        )
    ).scalar_one()

    assert result["processed"] == 1
    assert image.url == product.main_image
    assert variant.processing_status == ProductImageProcessingStatus.READY.value


@pytest.mark.asyncio
async def test_yandex_feed_backfill_reports_product_without_source(sqlite_session):
    product = await _make_product(sqlite_session, 92)

    result = await YandexFeedImageService.backfill(
        sqlite_session,
        execute=False,
        product_id=product.id,
    )

    assert result["planned"] == 0
    assert result["missing_sources"][0]["product_id"] == product.id


@pytest.mark.asyncio
async def test_yandex_feed_backfill_records_failed_source_without_picture_url(
    sqlite_session,
):
    product = await _make_product(sqlite_session, 93)
    source_url = "/media/products/shared/missing-yandex-source.webp"
    product.main_image = source_url
    image = ProductImage(product_id=product.id, url=source_url)
    sqlite_session.add_all([product, image])
    await sqlite_session.commit()

    result = await YandexFeedImageService.backfill(
        sqlite_session,
        execute=True,
        product_id=product.id,
    )
    variant = (
        await sqlite_session.execute(
            select(ProductImageVariant).where(
                ProductImageVariant.product_image_id == image.id,
                ProductImageVariant.variant_type
                == ProductImageVariantType.YANDEX_FEED.value,
            )
        )
    ).scalar_one()

    assert result["processed"] == 0
    assert result["errors"][0]["product_id"] == product.id
    assert variant.processing_status == ProductImageProcessingStatus.FAILED.value
    assert variant.url is None


@pytest.mark.asyncio
async def test_yandex_feed_backfill_continues_after_source_error(
    sqlite_session,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    missing = await _make_product(sqlite_session, 95)
    good = await _make_product(sqlite_session, 96)
    missing.main_image = "/media/products/shared/missing-batch-source.webp"
    good.main_image = _write_source_image(tmp_path, "good-batch-source.webp")
    sqlite_session.add_all(
        [
            missing,
            good,
            ProductImage(product_id=missing.id, url=missing.main_image),
            ProductImage(product_id=good.id, url=good.main_image),
        ]
    )
    await sqlite_session.commit()

    result = await YandexFeedImageService.backfill(
        sqlite_session,
        execute=True,
        limit=10,
        storage=_FakeProductMediaStorage(),
    )

    assert result["processed"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["product_id"] == missing.id
    assert result["processed_items"][0]["product_id"] == good.id
