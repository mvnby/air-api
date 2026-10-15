from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.manager_tenant_catalog import (
    ManagerTenantCatalogListResponse,
    ManagerTenantCatalogProductDetailResponse,
)
from core.database import get_session
from core.security import AuthenticatedUser, get_current_manager_tenant_scope, require_manager_access
from routers.manager_operation_ids import GET_MANAGER_TENANT_CATALOG_PRODUCT, LIST_MANAGER_TENANT_CATALOG_PRODUCTS
from services.manager_capability_service import ManagerCapabilityService
from services.manager_tenant_catalog_reader import ManagerTenantCatalogReader
from services.manager_tenant_catalog_service import ManagerTenantCatalogService
from services.tenant_scope_service import TenantScope


router = APIRouter(
    prefix="/api/manager/tenant-catalog",
    tags=["manager tenant catalog"],
)


@router.get(
    "/products",
    response_model=ManagerTenantCatalogListResponse,
    operation_id=LIST_MANAGER_TENANT_CATALOG_PRODUCTS,
)
async def list_manager_tenant_catalog_products(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=40, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    allowed: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read published master products with the selected storefront’s offer projection,
    paginated with limit 1–100. For partners, allowed means an active published offer whose
    grant is active or absent; an inactive linked grant hides that offer from the
    projection. For the system tenant allowed follows master publication and the allowed
    filter is ignored. No grant or offer is created.

    Access and scope: Manager access is required; data is restricted to the authenticated
    tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await ManagerTenantCatalogService.list_products(
        session,
        tenant_scope=tenant_scope,
        page=page,
        limit=limit,
        search=search,
        allowed=allowed,
    )


@router.get(
    "/products/{product_id}",
    response_model=ManagerTenantCatalogProductDetailResponse,
    operation_id=GET_MANAGER_TENANT_CATALOG_PRODUCT,
)
async def get_manager_tenant_catalog_product(
    product_id: int = Path(ge=1),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    """Read one product's plain-text description, public gallery, manuals and complete
    technical specifications. Requires Manager access and catalog.master.read capability.
    Partners can browse published master content; allowed and effective_price use only
    the authenticated tenant's selected storefront and valid offer/grant. System staff
    may also read unpublished master content. Missing or unpublished partner products
    return 404; invalid IDs return 422 and missing capability returns 403.

    selection_item is the current eligible published complete-split decision projection,
    including its existing demo cost masking. Other products return null. No grants,
    offers, selection or product data are created; GET is safe to repeat, including in
    read-only demo accounts. Source provenance, raw supplier records and credentials
    are excluded from the content projection.

    Access and scope: authenticated tenant and selected storefront; see [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    if ManagerCapabilityService.CATALOG_MASTER_READ not in ManagerCapabilityService.for_auth(auth):
        raise HTTPException(status_code=403, detail="Catalog read access required")
    payload = await ManagerTenantCatalogReader.get_product(
        session, product_id=product_id, tenant_scope=tenant_scope,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return payload
