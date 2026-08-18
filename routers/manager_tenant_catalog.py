from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.manager_tenant_catalog import ManagerTenantCatalogListResponse
from core.database import get_session
from core.security import get_current_manager_tenant_scope
from routers.manager_operation_ids import LIST_MANAGER_TENANT_CATALOG_PRODUCTS
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
    return await ManagerTenantCatalogService.list_products(
        session,
        tenant_scope=tenant_scope,
        page=page,
        limit=limit,
        search=search,
        allowed=allowed,
    )
