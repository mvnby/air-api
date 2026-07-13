"""Public order endpoints split from the main API router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from schemas import OrderPayload, OrderResponse, PublicOrderPricingErrorResponse
from services.installation_pricing_service import InstallationPricingError
from services.website_order_service import WebsiteOrderService

router = APIRouter(tags=["api"])


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
async def create_order(payload: OrderPayload, session: AsyncSession = Depends(get_session)):
    """
    Create a new order from website.
    Accepts customer information and cart items.
    """
    try:
        return await WebsiteOrderService.create_order(session, payload)
    except InstallationPricingError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
