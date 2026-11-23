from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.personal_offers import PublicPersonalOfferResponse
from core.database import get_session
from core.storefront_request_envelope import private_storefront_response_headers
from core.tenant_scope import VerifiedPublicStorefrontRequest, verify_public_storefront_request
from models.tenancy import TenantScope
from services.personal_offer_service import PersonalOfferService


router = APIRouter(tags=["api"])


@router.get(
    "/v1/personal-offers/{token}",
    response_model=PublicPersonalOfferResponse,
    operation_id="get_public_personal_offer",
)
async def get_public_personal_offer(
    token: str,
    response: Response,
    verified: VerifiedPublicStorefrontRequest = Depends(verify_public_storefront_request),
    session: AsyncSession = Depends(get_session),
):
    """Return a published offer only for its exact signed storefront host and active token."""
    headers = {
        **private_storefront_response_headers(),
        "X-Robots-Tag": "noindex, nofollow",
        "Referrer-Policy": "no-referrer",
    }
    context = verified.context
    if not verified.signed or context is None:
        raise HTTPException(401, "Invalid storefront context", headers=headers)
    offer = await PersonalOfferService.read_public(
        session, TenantScope(tenant_id=context.tenant_id, storefront_id=context.storefront_id),
        context.hostname, token,
    )
    if offer is None:
        raise HTTPException(404, "Offer unavailable", headers=headers)
    response.headers.update(headers)
    return offer
