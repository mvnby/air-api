from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.tenant_scope import (
    get_public_tenant_scope,
    verify_public_storefront_request,
)
from models.tenancy import TenantScope
from schemas_tenancy import PublicStorefrontContextResponse
from services.storefront_context_service import StorefrontContextService


router = APIRouter(
    tags=["api"],
    dependencies=[Depends(verify_public_storefront_request)],
)


@router.get(
    "/v1/storefront/context",
    response_model=PublicStorefrontContextResponse,
    operation_id="get_public_storefront_context",
)
async def get_public_storefront_context(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
) -> PublicStorefrontContextResponse:
    """
    Resolve public tenant/storefront identity, locale, currency and hostname from the
    current storefront scope. Returns 404 when that storefront is unavailable; the caller
    cannot select an arbitrary tenant in the body.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
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
