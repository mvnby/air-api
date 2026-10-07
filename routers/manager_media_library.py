import json
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    BACKFILL_REFERENCED_MEDIA_ASSETS,
    CROP_MEDIA_ASSET,
    DELETE_MEDIA_ASSET,
    GET_MEDIA_BACKGROUND_REMOVAL_CONFIG,
    LIST_MEDIA_ASSETS,
    REMOVE_MEDIA_ASSET_BACKGROUND,
    UPDATE_MEDIA_ASSET,
    UPLOAD_MEDIA_ASSET_FROM_URL,
    UPLOAD_MEDIA_ASSETS,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    ManagerActionMessageResponse,
    ManagerBackgroundRemovalConfigResponse,
    ManagerMediaAssetCropPayload,
    ManagerMediaBackfillReferencedAssetsResponse,
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


router = APIRouter(
    prefix="/api/manager/media/assets",
    tags=["manager media"],
    route_class=ManagerPermissionRoute,
)
MAX_UPLOAD_IMAGE_BYTES = 20 * 1024 * 1024


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
    """
    Read the platform media library with title/text, kind, tag and status filters, ordered
    newest first. page starts at 1 and limit is 1–100; usage_count describes known URL
    references. This system route lists platform-wide assets, including scoped assets,
    rather than filtering by selected storefront.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
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
    """
    Upload exactly one image per multipart request (despite the files array). The source is
    limited to 20 MB and tags_json must be a JSON array; violations or invalid/unsafe
    image/SVG returns 400. Stores a ready original asset in managed library storage; SVG is
    sanitized and retained as vector. Each call creates asset metadata even when storage
    deduplicates bytes.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        tags = json.loads(tags_json or "[]")
        if not isinstance(tags, list):
            raise ValueError("tags_json must be a JSON array")
        if len(files) != 1:
            raise ValueError("Upload exactly one image per request")

        upload = files[0]
        try:
            content = await upload.read(MAX_UPLOAD_IMAGE_BYTES + 1)
            if len(content) > MAX_UPLOAD_IMAGE_BYTES:
                raise ValueError("Uploaded image is too large (maximum 20 MB)")
            return await MediaLibraryService.upload_assets(
                session=session,
                files=[(upload.filename, content)],
                kind=kind,
                tags=[str(item) for item in tags],
                created_by=username,
            )
        finally:
            await upload.close()
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
    """
    Fetch an HTTP(S) image from a public-network source and store it as a ready original
    library asset. Redirects, MIME and size are checked; localhost/private-network sources
    are rejected. Invalid source/content returns 400 and runtime storage failure 500. This
    saves an asset rather than linking it to a product; no idempotency receipt exists.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
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


@router.post(
    "/backfill-references",
    response_model=ManagerMediaBackfillReferencedAssetsResponse,
    operation_id=BACKFILL_REFERENCED_MEDIA_ASSETS,
)
async def backfill_referenced_media_assets(
    execute: bool = Query(False),
    limit: int = Query(500, ge=1, le=5000),
    include_remote: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Index existing catalog/content media references into library metadata without rewriting
    their URLs. execute defaults to false and reports a plan; true creates up to limit
    (1–5000) metadata records. Already indexed URLs are skipped; include_remote controls
    recognition of remote references, not remote downloads. This is a synchronous backfill,
    not ordinary upload or physical cleanup.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    return await MediaLibraryService.backfill_referenced_assets(
        session=session,
        execute=execute,
        limit=limit,
        include_remote=include_remote,
        created_by=username,
    )


@router.get(
    "/background-removal/options",
    response_model=ManagerBackgroundRemovalConfigResponse,
    operation_id=GET_MEDIA_BACKGROUND_REMOVAL_CONFIG,
)
async def get_media_background_removal_config(
    _username: str = Depends(get_current_username),
):
    """
    Read configured/default background-removal provider, rembg models/process mode and
    preload options. No image is processed, model configuration changed or worker job
    started by this request.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return {
        "default_provider": resolve_background_removal_provider("auto"),
        "default_rembg_model": default_rembg_model_name(),
        "rembg_process_mode": rembg_process_mode(),
        "preload_models": rembg_preload_model_names(),
        "provider_options": background_removal_provider_options(),
        "rembg_models": rembg_model_options(include_experimental=True),
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
    """
    Update non-null metadata fields and replace tags when supplied; file bytes and URL
    remain unchanged. Empty alt_text/description clears their value; null fields are
    ignored. Missing asset returns 404; changing the kind of an in-use storefront_logo
    returns 400. This global route can edit asset metadata across storefronts.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
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
    """
    Crop a raster source and create a separate crop child asset, preserving the parent
    asset. Crop coordinates are clamped to source bounds; SVG cropping is rejected. Missing
    asset returns 404; unavailable/invalid source returns 400. The new processing variant is
    not an original publication URL; repeating creates another metadata asset.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
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
    """
    Synchronously remove a raster source background using provider/model and create a
    processed child asset. The source is preserved; no product/brand/series reference is
    automatically switched. Missing asset returns 404, invalid source/SVG/provider returns
    400 and runtime conflict 409. Processed library variants differ from permitted original
    publication URLs; repeats create new metadata.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
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
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
    """
    Delete library metadata, detach child parent references and attempt to remove the
    underlying local file only when no references remain. Missing asset returns 404; known
    usage blocks deletion with 409 unless force=true. force bypasses metadata usage
    protection but never deletion of an in-use storefront logo. It does not delete child
    assets or rewrite content references.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await MediaLibraryService.delete_asset(session=session, asset_id=asset_id, force=force)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
