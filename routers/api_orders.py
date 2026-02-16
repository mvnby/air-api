"""Public order endpoints split from the main API router."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from schemas import OrderPayload, OrderResponse
from services.website_order_service import WebsiteOrderService

router = APIRouter(tags=["api"])


@router.post("/v1/orders", response_model=OrderResponse, operation_id="create_order")
async def create_order(payload: OrderPayload, session: AsyncSession = Depends(get_session)):
    """
    Create a new order from website.
    Accepts customer information and cart items.
    """
    return await WebsiteOrderService.create_order(session, payload)
