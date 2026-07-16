"""Private, versioned use-case API consumed by the Telegram bot service."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot import (
    BotApiHealthResponse,
    BotCatalogProductLookupResponse,
    BotCatalogProductResponse,
    BotCatalogSearchRequest,
    BotCatalogSearchResponse,
    BotStaffContextResponse,
)
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from services.bot_access_service import BotAccessService
from services.bot_catalog_service import BotCatalogAccessDeniedError, BotCatalogService


router = APIRouter(
    prefix="/api/internal/bot/v1",
    tags=["internal bot v1"],
    dependencies=[Depends(require_bot_api_token)],
)


@router.get(
    "/health",
    response_model=BotApiHealthResponse,
    operation_id="get_internal_bot_api_health_v1",
)
async def get_internal_bot_api_health() -> BotApiHealthResponse:
    return BotApiHealthResponse()


@router.get(
    "/staff/context/{telegram_id}",
    response_model=BotStaffContextResponse,
    operation_id="get_internal_bot_staff_context_v1",
)
async def get_internal_bot_staff_context(
    telegram_id: int = Path(ge=1),
    session: AsyncSession = Depends(get_session),
) -> BotStaffContextResponse:
    context = await BotAccessService.get_context(session, telegram_id)
    return BotStaffContextResponse(
        telegram_id=context.telegram_id,
        is_staff=context.is_staff,
        display_name=context.display_name,
        primary_role=context.primary_role,
        roles=context.roles,
        legacy_installer_id=context.legacy_installer_id,
        is_manager=context.is_manager,
        is_executor=context.is_executor,
    )


@router.post(
    "/catalog/search",
    response_model=BotCatalogSearchResponse,
    operation_id="search_internal_bot_catalog_v1",
)
async def search_internal_bot_catalog(
    payload: BotCatalogSearchRequest,
    session: AsyncSession = Depends(get_session),
) -> BotCatalogSearchResponse:
    try:
        products = await BotCatalogService.search_for_staff(
            session,
            telegram_id=payload.telegram_id,
            query=payload.query,
            limit=payload.limit,
        )
    except BotCatalogAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return BotCatalogSearchResponse(
        items=[BotCatalogProductResponse.model_validate(product) for product in products]
    )


@router.get(
    "/catalog/products/{product_id}",
    response_model=BotCatalogProductLookupResponse,
    operation_id="get_internal_bot_catalog_product_v1",
)
async def get_internal_bot_catalog_product(
    product_id: int = Path(ge=1),
    telegram_id: int = Query(ge=1),
    session: AsyncSession = Depends(get_session),
) -> BotCatalogProductLookupResponse:
    try:
        product = await BotCatalogService.get_product_for_staff(
            session,
            telegram_id=telegram_id,
            product_id=product_id,
        )
    except BotCatalogAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return BotCatalogProductLookupResponse(
        product=BotCatalogProductResponse.model_validate(product) if product else None
    )
