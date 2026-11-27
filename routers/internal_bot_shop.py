"""Read-only catalog for a Telegram manager in the selected company and storefront."""

from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot_shop import (
    BotShopBrowseRequest, BotShopBrowseResponse, BotShopFacetsRequest, BotShopFacetsResponse,
    BotShopProductRequest, BotShopProductResponse, BotShopResolveRequest, BotShopResolveResponse,
)
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from services import bot_shop_service
from services.bot_api_access import BotUseCaseAccessDeniedError
from services.bot_business_context import bind_bot_business_context


router = APIRouter(
    prefix="/api/internal/bot/v1/shop", tags=["internal bot v1"],
    dependencies=[Depends(require_bot_api_token), Depends(bind_bot_business_context, scope="function")],
)


@contextmanager
def _shop_access():
    try:
        yield
    except BotUseCaseAccessDeniedError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/browse", response_model=BotShopBrowseResponse, operation_id="browse_internal_bot_shop_v1")
async def browse_internal_bot_shop(payload: BotShopBrowseRequest, session: AsyncSession = Depends(get_session)):
    """Browse eligible complete split systems at the selected storefront's retail prices.
    The service bearer, an active Telegram Manager and the current context version are
    required (401, 403 or 409). Filters apply before counts, sorting and pagination.
    Stock defaults to in_stock; availability=all includes orderable equipment. Feature
    IDs must all match. The page limit is 100; invalid filters return 422.
    """
    with _shop_access():
        return await bot_shop_service.browse(session, payload)


@router.post("/facets", response_model=BotShopFacetsResponse, operation_id="list_internal_bot_shop_facets_v1")
async def list_internal_bot_shop_facets(payload: BotShopFacetsRequest, session: AsyncSession = Depends(get_session)):
    """Find eligible brands, series, nominal cooling classes and effective equipment features.
    Counts and total use the same Manager catalog and retail/availability filters as browse.
    Brand, series and BTU options include alternatives in their own dimension. Cumulative
    feature counts describe the current result. Requires the service bearer, active Manager
    and current company/site version. Invalid filters return 422 and stale context 409.
    """
    with _shop_access():
        return await bot_shop_service.list_facets(session, payload)


@router.post("/products/resolve", response_model=BotShopResolveResponse, operation_id="resolve_internal_bot_shop_products_v1")
async def resolve_internal_bot_shop_products(payload: BotShopResolveRequest, session: AsyncSession = Depends(get_session)):
    """Resolve 1–100 distinct product IDs to current visible retail prices, photos and stock.
    Includes orderable products and preserves request order. Missing and ineligible models
    are omitted. This read requires a service bearer, active Manager and the current
    company/site version; duplicate IDs return 422 and stale context returns 409.
    """
    with _shop_access():
        return await bot_shop_service.resolve(session, payload)


@router.post("/products/{product_id}", response_model=BotShopProductResponse, operation_id="get_internal_bot_shop_product_v1")
async def get_internal_bot_shop_product(
    payload: BotShopProductRequest, product_id: int = Path(gt=0), session: AsyncSession = Depends(get_session),
):
    """Read the eligible model's current retail price, approved gallery, registered technical
    specifications and effective catalog features. Includes orderable equipment. Missing
    models and those outside the selected storefront catalog return 404. Requires the service
    bearer, active Manager and current company/site version (401, 403, 409 respectively).
    """
    with _shop_access():
        result = await bot_shop_service.detail(session, product_id, payload)
    if result is None:
        raise HTTPException(404, "Модель недоступна в выбранном каталоге")
    return result
