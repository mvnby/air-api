from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access, require_owner_access
from schemas import ManagerMediaAssetUploadResponse
from schemas_storefront_settings import StorefrontBrandResponse, StorefrontSettingsPayload, StorefrontSettingsResponse
from services.storefront_settings_service import StorefrontSettingsService
from services.media_library_service import MediaLibraryService
from routers import manager_operation_ids as operation_ids


router = APIRouter(prefix="/api/manager/storefront-settings", tags=["manager-storefront-settings"])


@router.get("/brand", response_model=StorefrontBrandResponse, operation_id=operation_ids.GET_MANAGER_STOREFRONT_BRAND)
async def get_storefront_brand(
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    settings = await StorefrontSettingsService.get_settings(session, tenant_scope=auth.tenant_scope())
    return StorefrontBrandResponse(
        display_name=settings.site.display_name,
        logo_url=settings.site.logo_url,
        compact_logo_url=settings.site.compact_logo_url,
    )


@router.post("/logo", response_model=ManagerMediaAssetUploadResponse, operation_id=operation_ids.UPLOAD_MANAGER_STOREFRONT_LOGO)
async def upload_storefront_logo(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_owner_access),
):
    try:
        content = await file.read(20 * 1024 * 1024 + 1)
        if len(content) > 20 * 1024 * 1024:
            raise ValueError("Логотип не должен превышать 20 МБ")
        return await MediaLibraryService.upload_assets(
            session,
            files=[(file.filename, content)],
            kind="storefront_logo",
            tags=[],
            created_by=auth.username,
            tenant_scope=auth.tenant_scope(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()


@router.get("", response_model=StorefrontSettingsResponse, operation_id=operation_ids.GET_MANAGER_STOREFRONT_SETTINGS)
async def get_storefront_settings(
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_owner_access),
):
    return await StorefrontSettingsService.get_settings(session, tenant_scope=auth.tenant_scope())


@router.put("", response_model=StorefrontSettingsResponse, operation_id=operation_ids.UPDATE_MANAGER_STOREFRONT_SETTINGS)
async def update_storefront_settings(
    payload: StorefrontSettingsPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_owner_access),
):
    return await StorefrontSettingsService.update_settings(
        session,
        tenant_scope=auth.tenant_scope(),
        payload=payload,
        actor_username=auth.username,
        actor_staff_user_id=auth.staff_user_id,
    )
