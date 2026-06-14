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
