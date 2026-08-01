from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.tenant_scope import get_public_tenant_scope
from models.tenancy import TenantScope
from schemas_tenancy import PublicStorefrontContextResponse
from services.storefront_context_service import StorefrontContextService


router = APIRouter(tags=["api"])


@router.get(
    "/v1/storefront/context",
    response_model=PublicStorefrontContextResponse,
    operation_id="get_public_storefront_context",
)
async def get_public_storefront_context(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
) -> PublicStorefrontContextResponse:
    context = await StorefrontContextService.resolve_by_scope(
        session,
        tenant_id=tenant_scope.tenant_id,
        storefront_id=tenant_scope.storefront_id,
    )
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storefront is unavailable",
        )
    return PublicStorefrontContextResponse(
        tenant_slug=context.tenant_slug,
        tenant_kind=context.tenant_kind,
        storefront_slug=context.storefront_slug,
        display_name=context.storefront_name,
        hostname=context.hostname,
        city=context.city,
        default_locale=context.default_locale,
        currency=context.currency,
    )
