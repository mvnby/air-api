from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

import models  # noqa: F401
from models import Product, ProductImage
from services.manager_media_service import ManagerMediaService
from services.product_image_processing_provider import ProductImageProcessingResult
from services.product_original_media_service import ProductOriginalMediaService


def image_bytes(size=(120, 90), color=(30, 120, 210)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def transparent_image_bytes(size=(80, 60)) -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", size, (30, 120, 210, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
async def sqlite_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / "media" / "products" / "source.png"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(image_bytes())

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def make_product_with_image(session: AsyncSession) -> tuple[Product, ProductImage]:
    product = Product(
        title="Crop Test",
        slug="crop-test",
        price=1000,
        main_image="/media/products/source.png",
        images=["/media/products/source.png"],
    )
    session.add(product)
    await session.flush()

    image = ProductImage(
        product_id=product.id,
        url="/media/products/source.png",
    )
    session.add(image)
    await session.commit()
    await session.refresh(product)
    await session.refresh(image)
    return product, image


@pytest.mark.asyncio
async def test_crop_gallery_image_appends_new_product_image(sqlite_session):
    product, source_image = await make_product_with_image(sqlite_session)

    result = await ManagerMediaService.crop_gallery_image(
        sqlite_session,
        source_image.id,
        x=10,
        y=10,
        width=50,
        height=40,
        mode="append",
    )

    rows = (
        await sqlite_session.execute(
            select(ProductImage).where(ProductImage.product_id == product.id)
        )
    ).scalars().all()
    await sqlite_session.refresh(product)

    assert result["id"] != source_image.id
    assert result["url"].startswith("/media/products/shared/")
    assert len(rows) == 2
    assert product.main_image == "/media/products/source.png"


@pytest.mark.asyncio
async def test_crop_gallery_image_replaces_source_and_main_image(sqlite_session):
    product, source_image = await make_product_with_image(sqlite_session)

    result = await ManagerMediaService.crop_gallery_image(
        sqlite_session,
        source_image.id,
        x=5,
        y=5,
        width=60,
        height=50,
        mode="replace",
    )

    await sqlite_session.refresh(product)
    await sqlite_session.refresh(source_image)

    assert result["id"] == source_image.id
    assert result["url"].startswith("/media/products/shared/")
    assert source_image.url == result["url"]
    assert product.main_image == result["url"]
    assert product.images == [result["url"]]
    assert Path("media/products/source.png").exists()


@pytest.mark.asyncio
async def test_crop_gallery_image_downloads_remote_source(sqlite_session, monkeypatch):
    product = Product(
        title="Remote Crop Test",
        slug="remote-crop-test",
        price=1000,
        main_image="https://example.com/source.png",
        images=["https://example.com/source.png"],
    )
    sqlite_session.add(product)
    await sqlite_session.flush()
    source_image = ProductImage(
        product_id=product.id,
        url="https://example.com/source.png",
    )
    sqlite_session.add(source_image)
    await sqlite_session.commit()
    await sqlite_session.refresh(product)
    await sqlite_session.refresh(source_image)

    async def fake_load_source_content(_url: str) -> bytes:
        return image_bytes(size=(160, 120))

    monkeypatch.setattr(
        ManagerMediaService,
        "load_image_source_content",
        staticmethod(fake_load_source_content),
    )

    result = await ManagerMediaService.crop_gallery_image(
        sqlite_session,
        source_image.id,
        x=10,
        y=10,
        width=70,
        height=60,
        mode="append",
        set_main=True,
    )

    await sqlite_session.refresh(product)

    assert result["url"].startswith("/media/products/shared/")
    assert product.main_image == result["url"]


@pytest.mark.asyncio
async def test_remove_background_gallery_image_replaces_source_and_main_image(
    sqlite_session,
    monkeypatch,
):
    product, source_image = await make_product_with_image(sqlite_session)

    class FakeProcessor:
        provider_name = "fake"

        async def process(self, *, source_content, context):
            return ProductImageProcessingResult(
                content=transparent_image_bytes(size=(72, 54)),
                extension="webp",
                width=72,
                height=54,
            )

    monkeypatch.setattr(
        "services.manager_media_service.get_product_image_processor",
        lambda *_args, **_kwargs: FakeProcessor(),
    )

    result = await ManagerMediaService.remove_background_gallery_image(
        sqlite_session,
        source_image.id,
        provider="rembg",
        mode="replace",
    )

    await sqlite_session.refresh(product)
    await sqlite_session.refresh(source_image)
    rows = (
        await sqlite_session.execute(
            select(ProductImage).where(ProductImage.product_id == product.id)
        )
    ).scalars().all()

    assert result["id"] == source_image.id
    assert result["url"].startswith("/media/products/shared/")
    assert source_image.url == result["url"]
    assert product.main_image == result["url"]
    assert product.images == [result["url"]]
    assert len(rows) == 1
    assert Path("media/products/source.png").exists()


@pytest.mark.asyncio
async def test_product_original_webp_preserves_alpha(sqlite_session):
    original = await ProductOriginalMediaService.save_shared_original(
        transparent_image_bytes(size=(40, 30))
    )

    with Image.open(BytesIO(original.content)) as image:
        assert image.mode == "RGBA"
