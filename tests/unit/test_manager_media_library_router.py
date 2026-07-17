from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, UploadFile

from routers.manager_media_library import MAX_UPLOAD_IMAGE_BYTES, upload_media_assets
from services.media_library_service import MediaLibraryService


@pytest.mark.asyncio
async def test_upload_media_assets_rejects_batch_before_reading(monkeypatch):
    first = UploadFile(filename="first.jpg", file=AsyncMock())
    second = UploadFile(filename="second.jpg", file=AsyncMock())
    upload_assets = AsyncMock()
    monkeypatch.setattr(MediaLibraryService, "upload_assets", upload_assets)

    with pytest.raises(HTTPException) as exc_info:
        await upload_media_assets(
            files=[first, second],
            kind="brand",
            tags_json="[]",
            session=AsyncMock(),
            username="manager",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Upload exactly one image per request"
    upload_assets.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_media_assets_caps_source_file_size(monkeypatch):
    upload = AsyncMock()
    upload.filename = "oversized.jpg"
    upload.read.return_value = b"x" * (MAX_UPLOAD_IMAGE_BYTES + 1)
    upload_assets = AsyncMock()
    monkeypatch.setattr(MediaLibraryService, "upload_assets", upload_assets)

    with pytest.raises(HTTPException) as exc_info:
        await upload_media_assets(
            files=[upload],
            kind="brand",
            tags_json="[]",
            session=AsyncMock(),
            username="manager",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Uploaded image is too large (maximum 20 MB)"
    upload.read.assert_awaited_once_with(MAX_UPLOAD_IMAGE_BYTES + 1)
    upload.close.assert_awaited_once()
    upload_assets.assert_not_awaited()
