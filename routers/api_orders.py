"""Public order endpoints split from the main API router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.tenant_scope import (
    get_public_tenant_scope,
    verify_public_storefront_request,
)
from schemas import OrderPayload, OrderResponse, PublicOrderPricingErrorResponse
from services.installation_pricing_service import InstallationPricingError
from services.website_order_service import WebsiteOrderService
from services.tenant_scope_service import TenantScope

router = APIRouter(
    tags=["api"],
    dependencies=[Depends(verify_public_storefront_request)],
)


@router.post(
    "/v1/orders",
    response_model=OrderResponse,
    operation_id="create_order",
    responses={
        409: {
            "model": PublicOrderPricingErrorResponse,
            "description": "The selected installation quote conflicts with current tariffs.",
        }
    },
)
async def create_order(
    payload: OrderPayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Create a new order from website.
    Accepts customer information and cart items.
    """
    try:
        return await WebsiteOrderService.create_order(
            session,
            payload,
            tenant_scope=tenant_scope,
        )
    except InstallationPricingError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
