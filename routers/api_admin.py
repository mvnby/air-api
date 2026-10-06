"""Admin/search/health endpoints split from the main API router."""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from api_contracts.public_catalog import PublicProductSearchResponse
from core.database import get_session
from core.security import get_current_username
from core.tenant_scope import get_public_tenant_scope
from models.tenancy import TenantScope
from services.admin_api_service import AdminApiService
from services.public_catalog_service import PublicCatalogService
from services.readiness_service import ReadinessService

router = APIRouter(tags=["api"])


@router.get("/products/search", response_model=PublicProductSearchResponse)
async def search_products(
    q: str = None,
    is_inverter: bool = None,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Search storefront-visible products using fuzzy matching and optional inverter filtering.
    Uses public tenant resolution; does not expose the unrestricted Manager catalog.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    products = await PublicCatalogService.search(
        session,
        tenant_scope=tenant_scope,
        query=q,
        is_inverter=is_inverter,
    )
    return PublicProductSearchResponse(items=products)


@router.get("/admin/tags/filterable")
async def get_filterable_tags(
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Read the shared filterable tag dictionary for authenticated Manager workflows. Requires
    get_current_username; this legacy /api/admin path is not a supplier integration surface.
    """
    return await AdminApiService.get_filterable_tags(session)


@router.get("/admin/products/search")
async def admin_search_products(
    q: str = "",
    tag_ids: List[int] = Query(None),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Search shared products by query and optional tag IDs for authenticated Manager
    workflows. Requires get_current_username; this legacy helper does not use the storefront
    catalog projection.
    """
    return await AdminApiService.search_products(session, q=q, tag_ids=tag_ids)


@router.get("/admin/services/search")
async def admin_search_services(
    q: str = "",
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Search shared services by query for authenticated Manager workflows. Requires
    get_current_username; this helper is not a public service tariff calculation.
    """
    return await AdminApiService.search_services(session, q=q)


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_session)):
    """
    Check API and database availability without business-data access. No Manager or bot
    token is required. Use /api/ready as the separate traffic-readiness check.
    """
    return await AdminApiService.health_check(session)


@router.get("/ready")
async def readiness_check(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Check whether this API node can receive public traffic, including database and scheduler
    runtime readiness. Returns the readiness service status and body (including non-success
    status when unready); no Manager or bot token is required.
    """
    status_code, payload = await ReadinessService.check(
        session,
        scheduler_runtime=getattr(request.app.state, "scheduler_runtime", None),
    )
    return JSONResponse(status_code=status_code, content=payload)
