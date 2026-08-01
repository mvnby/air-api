"""Public catalog revision endpoint."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.tenant_scope import (
    get_public_tenant_scope,
    verify_public_storefront_request,
)
from models.tenancy import TenantScope
from schemas import CatalogRevisionResponse
from services.catalog_revision_service import CatalogRevisionService


router = APIRouter(
    tags=["api"],
    dependencies=[Depends(verify_public_storefront_request)],
)


@router.get(
    "/v1/catalog/revision",
    response_model=CatalogRevisionResponse,
    operation_id="get_catalog_revision",
)
async def get_catalog_revision(
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    payload = await CatalogRevisionService.get_contextual(
        session,
        tenant_scope=tenant_scope,
    )
    response.headers["X-Catalog-Revision"] = str(payload["revision"])
    response.headers["X-Storefront-Catalog-Revision"] = str(
        payload["storefront_revision"]
    )
    response.headers["ETag"] = f'W/"catalog-{payload["cache_key"]}"'
    if "no-store" not in response.headers.get("Cache-Control", "").lower():
        response.headers["Cache-Control"] = "private, no-cache, max-age=0"
    response.headers["Vary"] = "X-MVN-Storefront-Host"
    return payload
