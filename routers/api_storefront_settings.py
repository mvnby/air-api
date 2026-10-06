from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.tenant_scope import get_public_tenant_scope
from models.tenancy import TenantScope
from schemas_storefront_settings import StorefrontSettingsResponse
from services.storefront_settings_service import StorefrontSettingsService


router = APIRouter(tags=["storefront-settings"])


@router.get("/v1/storefront-settings", response_model=StorefrontSettingsResponse, operation_id="get_public_storefront_settings")
async def get_public_storefront_settings(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Read settings for the storefront selected by public tenant resolution, including its
    configured service availability.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    return await StorefrontSettingsService.get_settings(session, tenant_scope=tenant_scope)
