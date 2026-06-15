import json
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    CROP_MEDIA_ASSET,
    DELETE_MEDIA_ASSET,
    GET_MEDIA_BACKGROUND_REMOVAL_CONFIG,
    LIST_MEDIA_ASSETS,
    REMOVE_MEDIA_ASSET_BACKGROUND,
    UPDATE_MEDIA_ASSET,
    UPLOAD_MEDIA_ASSET_FROM_URL,
    UPLOAD_MEDIA_ASSETS,
)
from schemas import (
    ManagerActionMessageResponse,
    ManagerBackgroundRemovalConfigResponse,
    ManagerMediaAssetCropPayload,
    ManagerMediaAssetListResponse,
    ManagerMediaAssetResponse,
    ManagerMediaAssetUpdatePayload,
    ManagerMediaAssetUrlUploadPayload,
    ManagerMediaAssetUploadResponse,
)
from services.media_library_service import MediaLibraryService
from services.product_image_processing_provider import (
    background_removal_provider_options,
    default_rembg_model_name,
    rembg_model_options,
    rembg_process_mode,
    rembg_preload_model_names,
    resolve_background_removal_provider,
)


router = APIRouter(prefix="/api/manager/media/assets", tags=["manager media"])


@router.get(
    "",
    response_model=ManagerMediaAssetListResponse,
    operation_id=LIST_MEDIA_ASSETS,
)
async def list_media_assets(
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=100),
    q: str | None = Query(None),
    kind: str | None = Query(None),
    tag: str | None = Query(None),
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _username: str = Depends(get_current_username),
):
    return await MediaLibraryService.list_assets(
        session=session,
        page=page,
        limit=limit,
        query=q,
        kind=kind,
        tag=tag,
        status=status,
    )


@router.post(
    "",
    response_model=ManagerMediaAssetUploadResponse,
    operation_id=UPLOAD_MEDIA_ASSETS,
)
async def upload_media_assets(
    files: List[UploadFile] = File(...),
    kind: str = Form("misc"),
    tags_json: str = Form("[]"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    try:
        tags = json.loads(tags_json or "[]")
        if not isinstance(tags, list):
            raise ValueError("tags_json must be a JSON array")
        file_payloads = [(item.filename, await item.read()) for item in files]
        return await MediaLibraryService.upload_assets(
            session=session,
            files=file_payloads,
            kind=kind,
            tags=[str(item) for item in tags],
            created_by=username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/from-url",
    response_model=ManagerMediaAssetUploadResponse,
    operation_id=UPLOAD_MEDIA_ASSET_FROM_URL,
)
async def upload_media_asset_from_url(
    payload: ManagerMediaAssetUrlUploadPayload,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    try:
        return await MediaLibraryService.upload_asset_from_url(
            session=session,
            url=payload.url,
            kind=payload.kind,
            tags=payload.tags,
            created_by=username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/background-removal/options",
    response_model=ManagerBackgroundRemovalConfigResponse,
    operation_id=GET_MEDIA_BACKGROUND_REMOVAL_CONFIG,
)
async def get_media_background_removal_config(
    _username: str = Depends(get_current_username),
):
    return {
        "default_provider": resolve_background_removal_provider("auto"),
        "default_rembg_model": default_rembg_model_name(),
        "rembg_process_mode": rembg_process_mode(),
        "preload_models": rembg_preload_model_names(),
        "provider_options": background_removal_provider_options(),
        "rembg_models": rembg_model_options(),
    }


@router.patch(
    "/{asset_id}",
    response_model=ManagerMediaAssetResponse,
    operation_id=UPDATE_MEDIA_ASSET,
)
async def update_media_asset(
    asset_id: int,
    payload: ManagerMediaAssetUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _username: str = Depends(get_current_username),
):
    try:
        return await MediaLibraryService.update_asset(
            session=session,
            asset_id=asset_id,
            title=payload.title,
            alt_text=payload.alt_text,
            description=payload.description,
            kind=payload.kind,
            tags=payload.tags,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{asset_id}/crop",
    response_model=ManagerMediaAssetResponse,
    operation_id=CROP_MEDIA_ASSET,
)
async def crop_media_asset(
    asset_id: int,
    payload: ManagerMediaAssetCropPayload,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    try:
        return await MediaLibraryService.crop_asset(
            session=session,
            asset_id=asset_id,
            x=payload.x,
            y=payload.y,
            width=payload.width,
            height=payload.height,
            title=payload.title,
            created_by=username,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{asset_id}/remove-background",
    response_model=ManagerMediaAssetResponse,
    operation_id=REMOVE_MEDIA_ASSET_BACKGROUND,
)
async def remove_media_asset_background(
    asset_id: int,
    provider: str = Query("auto", description="Processing provider: auto, noop, manual, rembg, birefnet, ben"),
    rembg_model: str | None = Query(None, description="Optional rembg model override"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    try:
        return await MediaLibraryService.remove_background(
            session=session,
            asset_id=asset_id,
            created_by=username,
            provider=provider,
            rembg_model=rembg_model,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete(
    "/{asset_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MEDIA_ASSET,
)
async def delete_media_asset(
    asset_id: int,
    force: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    _username: str = Depends(get_current_username),
):
    try:
        return await MediaLibraryService.delete_asset(session=session, asset_id=asset_id, force=force)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
