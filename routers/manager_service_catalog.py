"""Owner-only detached service-template copying for the authenticated tenant."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import (
    AuthenticatedUser,
    get_current_manager_tenant_scope,
    require_owner_access,
)
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    CLONE_MANAGER_SERVICE_CATALOG_TEMPLATE,
    PREVIEW_MANAGER_SERVICE_CATALOG_TEMPLATE,
)
from schemas_service_catalog import (
    ManagerServiceCatalogClonePayload,
    ManagerServiceCatalogCloneResponse,
    ManagerServiceCatalogTemplatePreviewResponse,
)
from services.service_catalog_template_service import ServiceCatalogTemplateService


router = APIRouter(
    prefix="/api/manager/service-catalog",
    tags=["manager/service-catalog"],
    dependencies=[Depends(require_owner_access)],
)


@router.get(
    "/template-preview",
    response_model=ManagerServiceCatalogTemplatePreviewResponse,
    operation_id=PREVIEW_MANAGER_SERVICE_CATALOG_TEMPLATE,
)
async def preview_manager_service_catalog_template(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    return await ServiceCatalogTemplateService.preview(
        session,
        tenant_scope=tenant_scope,
    )


@router.post(
    "/clone-template",
    response_model=ManagerServiceCatalogCloneResponse,
    operation_id=CLONE_MANAGER_SERVICE_CATALOG_TEMPLATE,
)
async def clone_manager_service_catalog_template(
    payload: ManagerServiceCatalogClonePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
    auth: AuthenticatedUser = Depends(require_owner_access),
):
    return await ServiceCatalogTemplateService.clone(
        session,
        tenant_scope=tenant_scope,
        expected_fingerprint=payload.expected_fingerprint,
        actor_username=auth.username,
        actor_staff_user_id=auth.staff_user_id,
    )
