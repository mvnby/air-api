from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import AuthenticatedUser, require_owner_access
from schemas_storefront_settings import StorefrontSettingsPayload, StorefrontSettingsResponse
from services.storefront_settings_service import StorefrontSettingsService
from routers import manager_operation_ids as operation_ids


router = APIRouter(prefix="/api/manager/storefront-settings", tags=["manager-storefront-settings"])


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
