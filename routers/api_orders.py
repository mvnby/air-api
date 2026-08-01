"""Public order endpoints split from the main API router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.public_write_idempotency import get_public_write_idempotency_key
from core.tenant_scope import (
    get_public_tenant_scope,
    verify_public_storefront_request,
)
from schemas import (
    OrderPayload,
    OrderResponse,
    PublicOrderPricingErrorResponse,
)
from schemas_public_checkout import PublicWriteIdempotencyErrorResponse
from services.installation_pricing_service import InstallationPricingError
from services.website_order_service import WebsiteOrderService
from services.tenant_scope_service import TenantScope
from services.public_write_idempotency_service import (
    PublicWriteIdempotencyConflict,
    PublicWriteIdempotencyUnavailable,
)

router = APIRouter(
    tags=["api"],
    dependencies=[Depends(verify_public_storefront_request)],
)

_IDEMPOTENCY_UNAVAILABLE_RESPONSE = {
    "description": "Request can be retried after a short delay",
    "headers": {
        "Retry-After": {
            "description": "Delay in seconds before retrying the same command",
            "schema": {"type": "string"},
        }
    },
}


@router.post(
    "/v1/orders",
    response_model=OrderResponse,
    operation_id="create_order",
    responses={
        400: {"description": "Invalid idempotency key"},
        409: {
            "model": (
                PublicOrderPricingErrorResponse
                | PublicWriteIdempotencyErrorResponse
            ),
            "description": (
                "Installation pricing conflict or Idempotency-Key reused with "
                "different content."
            ),
        },
        503: _IDEMPOTENCY_UNAVAILABLE_RESPONSE,
    },
)
async def create_order(
    payload: OrderPayload,
    idempotency_key: str = Depends(get_public_write_idempotency_key),
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
            idempotency_key=idempotency_key,
        )
    except PublicWriteIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PublicWriteIdempotencyUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Приём заказа временно занят. Повторите отправку.",
            headers={"Retry-After": "1"},
        ) from exc
    except InstallationPricingError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
