from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers.manager_media_gallery_write import apply_gallery_to_series as apply_gallery_route
from routers.manager_media_gallery_write import cleanup_media as cleanup_media_route
from schemas import ManagerMediaCleanupResponse
from services.manager_media_service import ManagerMediaService
from services.product_image_variant_service import ProductImageVariantService


@pytest.mark.asyncio
async def test_apply_gallery_delete_unreferenced_fails_before_database_access():
    session = AsyncMock()

    with pytest.raises(RuntimeError, match="Physical media cleanup is deferred"):
        await ManagerMediaService.apply_gallery_to_series(
            session,
            product_id=42,
            delete_unreferenced=True,
        )

    session.get.assert_not_awaited()
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_gallery_router_exposes_deferred_cleanup_as_conflict(monkeypatch):
    apply_mock = AsyncMock(
        side_effect=RuntimeError("Physical media cleanup is deferred")
    )
    monkeypatch.setattr(ManagerMediaService, "apply_gallery_to_series", apply_mock)

    with pytest.raises(HTTPException) as exc_info:
        await apply_gallery_route(
            product_id=42,
            dry_run=False,
            delete_unreferenced=True,
            session=AsyncMock(),
            username="manager",
        )

    assert exc_info.value.status_code == 409
    assert "deferred" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_cleanup_execute_fails_before_scanning_database_or_files():
    session = AsyncMock()

    with pytest.raises(RuntimeError, match="Physical media GC is deferred"):
        await ManagerMediaService.cleanup_media(session, dry_run=False)

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_report_has_valid_empty_response_without_local_media_root(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    session = AsyncMock()

    result = await ManagerMediaService.cleanup_media(session, dry_run=True)

    assert ManagerMediaCleanupResponse.model_validate(result).model_dump() == {
        "dry_run": True,
        "deleted_count": 0,
        "reclaimed_bytes": 0,
        "files": [],
    }
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_route_supports_fresh_or_r2_only_runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session = AsyncMock()

    result = await cleanup_media_route(
        dry_run=True,
        session=session,
        username="manager",
    )

    assert ManagerMediaCleanupResponse.model_validate(result).deleted_count == 0
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_nested_variant_reprocess_requires_caller_owned_mutation_batch():
    session = AsyncMock()

    with pytest.raises(ValueError, match="caller-owned mutation_batch"):
        await ProductImageVariantService.reprocess_variant(
            session,
            product_image_id=42,
            commit=False,
        )

    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_nested_bulk_gallery_add_requires_caller_owned_mutation_batch():
    session = AsyncMock()

    with pytest.raises(ValueError, match="caller-owned mutation_batch"):
        await ManagerMediaService.bulk_add_gallery_images(
            session=session,
            product_ids=[42],
            source_urls=["/media/products/shared/example.webp"],
            is_installation=False,
            skip_existing=True,
            set_main=False,
            commit=False,
        )

    session.execute.assert_not_awaited()
