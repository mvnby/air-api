"""Public website lead capture endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from schemas import ProductAvailabilityLeadPayload, ProductAvailabilityLeadResponse
from services.website_lead_service import WebsiteLeadService

router = APIRouter(tags=["api"])


@router.post(
    "/v1/leads/product-availability",
    response_model=ProductAvailabilityLeadResponse,
    operation_id="create_product_availability_lead",
)
async def create_product_availability_lead(
    payload: ProductAvailabilityLeadPayload,
    session: AsyncSession = Depends(get_session),
):
    try:
        return await WebsiteLeadService.create_product_availability_lead(session, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
