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
    """
    Read canonical service-template fingerprint/counts and target-tenant state to determine
    whether a detached clone is available. This performs no writes. The system tenant cannot
    clone into itself; a partner target must be empty or already match a completed clone,
    and canonical drafts must match the current published book when one exists.

    Access and scope: owner/admin access is required in the authenticated tenant and
    selected storefront; partner owners may use this workflow. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
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
    """
    Copy the canonical template into the authenticated partner tenant as detached
    service-card/tariff/rule/rate data, including its own first published book when
    applicable. expected_fingerprint guards source changes; changed source, partial/nonempty
    incompatible target or system-tenant target returns 409, missing tenant/storefront 404.
    Source/target locks protect the atomic copy and audit. A complete matching prior clone
    returns already_cloned; later canonical edits do not synchronize into the copy.

    Access and scope: owner/admin access is required in the authenticated tenant and
    selected storefront; partner owners may use this workflow. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await ServiceCatalogTemplateService.clone(
        session,
        tenant_scope=tenant_scope,
        expected_fingerprint=payload.expected_fingerprint,
        actor_username=auth.username,
        actor_staff_user_id=auth.staff_user_id,
    )
