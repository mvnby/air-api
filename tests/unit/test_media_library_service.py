from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import models  # noqa: F401
from services import media_library_service
from services.media_library_service import MediaLibraryService


def image_bytes(size=(120, 80), color=(20, 180, 160)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def svg_bytes() -> bytes:
    return b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 80">
        <rect width="240" height="80" fill="#0f766e"/>
        <text x="24" y="52" fill="#fff">MVN</text>
    </svg>"""


class FakeBackgroundProcessor:
    provider_name = "ben"

    async def process(self, *, source_content: bytes, context):
        class Result:
            content = image_bytes(size=(48, 32), color=(200, 20, 80))
            extension = "webp"
            width = 48
            height = 32

        return Result()


@pytest.fixture
async def sqlite_session(tmp_path, monkeypatch):
    monkeypatch.setattr(media_library_service, "MEDIA_LIBRARY_BASE_DIR", tmp_path / "library")
    monkeypatch.setattr(media_library_service, "MEDIA_LIBRARY_PUBLIC_PREFIX", "/media/library")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_upload_and_list_media_assets(sqlite_session):
    response = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("install-photo.png", image_bytes())],
        kind="installation",
        tags=["монтаж", "штробы"],
        created_by="admin",
    )

    assert response["uploaded"] == 1
    item = response["items"][0]
    assert item["url"].startswith("/media/library/original/")
    assert item["kind"] == "installation"
    assert item["tags"] == ["монтаж", "штробы"]
    assert item["width"] == 120
    assert item["height"] == 80

    listing = await MediaLibraryService.list_assets(
        session=sqlite_session,
        kind="installation",
        tag="монтаж",
    )
    assert listing["meta"]["total"] == 1
    assert listing["items"][0]["id"] == item["id"]


@pytest.mark.asyncio
async def test_upload_svg_media_asset_keeps_vector_source(sqlite_session):
    response = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("brand-logo.svg", svg_bytes())],
        kind="brand",
        tags=["logo"],
        created_by="admin",
    )

    assert response["uploaded"] == 1
    item = response["items"][0]
    assert item["url"].startswith("/media/library/original/")
    assert item["url"].endswith(".svg")
    assert item["mime_type"] == "image/svg+xml"
    assert item["kind"] == "brand"
    assert item["tags"] == ["logo"]
    assert item["width"] == 240
    assert item["height"] == 80

    with pytest.raises(ValueError, match="SVG assets cannot be cropped"):
        await MediaLibraryService.crop_asset(
            session=sqlite_session,
            asset_id=item["id"],
            x=0,
            y=0,
            width=20,
            height=20,
            title="logo crop",
            created_by="admin",
        )


@pytest.mark.asyncio
async def test_upload_svg_media_asset_rejects_script(sqlite_session):
    with pytest.raises(ValueError, match="unsupported embedded content"):
        await MediaLibraryService.upload_assets(
            session=sqlite_session,
            files=[("unsafe.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')],
            kind="brand",
            tags=["logo"],
            created_by="admin",
        )


@pytest.mark.asyncio
async def test_upload_svg_media_asset_allows_internal_style_references(sqlite_session):
    content = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">
        <defs>
            <linearGradient id="brand"><stop offset="0" stop-color="#00a991"/></linearGradient>
        </defs>
        <rect width="16" height="16" style="fill:url(#brand)"/>
    </svg>"""

    response = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("gradient-logo.svg", content)],
        kind="brand",
        tags=["logo"],
        created_by="admin",
    )

    assert response["items"][0]["mime_type"] == "image/svg+xml"


@pytest.mark.asyncio
async def test_crop_media_asset_creates_variant(sqlite_session):
    upload = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("source.png", image_bytes(size=(200, 100)))],
        kind="article",
        tags=["обложка"],
        created_by="admin",
    )
    source = upload["items"][0]

    cropped = await MediaLibraryService.crop_asset(
        session=sqlite_session,
        asset_id=source["id"],
        x=20,
        y=10,
        width=60,
        height=40,
        title="source crop",
        created_by="admin",
    )

    assert cropped["parent_asset_id"] == source["id"]
    assert cropped["variant_type"] == "crop"
    assert cropped["original_url"] == source["url"]
    assert cropped["width"] == 60
    assert cropped["height"] == 40
    assert cropped["tags"] == ["обложка"]


@pytest.mark.asyncio
async def test_remove_background_uses_selected_provider(sqlite_session, monkeypatch):
    requested_providers = []

    def fake_get_processor(provider: str):
        requested_providers.append(provider)
        return FakeBackgroundProcessor()

    monkeypatch.setattr(media_library_service, "get_product_image_processor", fake_get_processor)
    upload = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("source.png", image_bytes(size=(160, 120)))],
        kind="product",
        tags=["товар"],
        created_by="admin",
    )
    source = upload["items"][0]

    processed = await MediaLibraryService.remove_background(
        session=sqlite_session,
        asset_id=source["id"],
        created_by="admin",
        provider="ben",
    )

    assert requested_providers == ["ben"]
    assert processed["parent_asset_id"] == source["id"]
    assert processed["variant_type"] == "background_removed"
    assert processed["width"] == 48
    assert processed["height"] == 32


@pytest.mark.asyncio
async def test_upload_media_asset_from_url_uses_existing_pipeline(sqlite_session, monkeypatch):
    monkeypatch.setattr(
        MediaLibraryService,
        "_validate_remote_image_url",
        staticmethod(lambda url: url),
    )

    async def fake_download(_url: str):
        return image_bytes(size=(90, 60)), "remote-photo.png"

    monkeypatch.setattr(
        MediaLibraryService,
        "_download_remote_image",
        staticmethod(fake_download),
    )

    response = await MediaLibraryService.upload_asset_from_url(
        session=sqlite_session,
        url="https://example.com/remote-photo.png",
        kind="service",
        tags=["обслуживание"],
        created_by="admin",
    )

    assert response["uploaded"] == 1
    item = response["items"][0]
    assert item["source_filename"] == "remote-photo.png"
    assert item["kind"] == "service"
    assert item["tags"] == ["обслуживание"]
    assert item["width"] == 90
    assert item["height"] == 60


@pytest.mark.asyncio
async def test_delete_parent_media_asset_keeps_variant(sqlite_session):
    upload = await MediaLibraryService.upload_assets(
        session=sqlite_session,
        files=[("source.png", image_bytes(size=(200, 100)))],
        kind="article",
        tags=["обложка"],
        created_by="admin",
    )
    source = upload["items"][0]
    cropped = await MediaLibraryService.crop_asset(
        session=sqlite_session,
        asset_id=source["id"],
        x=20,
        y=10,
        width=60,
        height=40,
        title="source crop",
        created_by="admin",
    )

    result = await MediaLibraryService.delete_asset(
        session=sqlite_session,
        asset_id=source["id"],
    )

    assert result["message"] == "Media asset deleted"
    listing = await MediaLibraryService.list_assets(session=sqlite_session)
    assert listing["meta"]["total"] == 1
    assert listing["items"][0]["id"] == cropped["id"]
    assert listing["items"][0]["parent_asset_id"] is None
