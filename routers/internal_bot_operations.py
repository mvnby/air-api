"""Private Telegram bot API for catalog and repair use cases."""

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot import (
    BotCatalogProductResponse,
    BotCuratedProductsRequest,
    BotCuratedProductsResponse,
    BotProductMutationRequest,
    BotProductMutationResponse,
    BotProductPriceUpdateRequest,
    BotProductSelectionRequest,
    BotProductSelectionResponse,
    BotRepairApplyRequest,
    BotRepairApplyResponse,
    BotRepairDraftRequest,
    BotRepairDraftResponse,
)
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from services.bot_api_access import BotUseCaseAccessDeniedError
from services.bot_catalog_operations_api_service import BotCatalogOperationsApiService
from services.bot_repair_context_api_service import BotRepairContextApiService


router = APIRouter(
    prefix="/api/internal/bot/v1",
    tags=["internal bot v1 operations"],
    dependencies=[Depends(require_bot_api_token)],
)


def _raise_use_case_error(exc: Exception) -> None:
    if isinstance(exc, BotUseCaseAccessDeniedError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/catalog/selection",
    response_model=BotProductSelectionResponse,
    operation_id="build_internal_bot_catalog_selection_v1",
)
async def build_catalog_selection(
    payload: BotProductSelectionRequest,
    session: AsyncSession = Depends(get_session),
) -> BotProductSelectionResponse:
    try:
        selection = await BotCatalogOperationsApiService.build_selection(
            session, telegram_id=payload.telegram_id, query=payload.query
        )
    except (BotUseCaseAccessDeniedError, ValueError) as exc:
        _raise_use_case_error(exc)
    return BotProductSelectionResponse(selection=selection)


@router.post(
    "/catalog/curated",
    response_model=BotCuratedProductsResponse,
    operation_id="get_internal_bot_curated_catalog_v1",
)
async def get_curated_catalog(
    payload: BotCuratedProductsRequest,
    session: AsyncSession = Depends(get_session),
) -> BotCuratedProductsResponse:
    try:
        products = await BotCatalogOperationsApiService.get_curated(
            session,
            telegram_id=payload.telegram_id,
            area=payload.area,
            is_inverter=payload.is_inverter,
            tag_slugs=payload.tag_slugs,
            limit=payload.limit,
        )
    except (BotUseCaseAccessDeniedError, ValueError) as exc:
        _raise_use_case_error(exc)
    return BotCuratedProductsResponse(
        items=[BotCatalogProductResponse.model_validate(product) for product in products]
    )


@router.post(
    "/catalog/products/{product_id}/price",
    response_model=BotProductMutationResponse,
    operation_id="update_internal_bot_catalog_product_price_v1",
)
async def update_catalog_product_price(
    payload: BotProductPriceUpdateRequest,
    product_id: int = Path(ge=1),
    session: AsyncSession = Depends(get_session),
) -> BotProductMutationResponse:
    try:
        changed = await BotCatalogOperationsApiService.update_price(
            session,
            telegram_id=payload.telegram_id,
            product_id=product_id,
            price=payload.price,
        )
    except (BotUseCaseAccessDeniedError, ValueError) as exc:
        _raise_use_case_error(exc)
    return BotProductMutationResponse(product_id=product_id, changed=changed)


@router.post(
    "/catalog/products/{product_id}/delete",
    response_model=BotProductMutationResponse,
    operation_id="delete_internal_bot_catalog_product_v1",
)
async def delete_catalog_product(
    payload: BotProductMutationRequest,
    product_id: int = Path(ge=1),
    session: AsyncSession = Depends(get_session),
) -> BotProductMutationResponse:
    try:
        changed = await BotCatalogOperationsApiService.delete_product(
            session, telegram_id=payload.telegram_id, product_id=product_id
        )
    except (BotUseCaseAccessDeniedError, ValueError) as exc:
        _raise_use_case_error(exc)
    return BotProductMutationResponse(product_id=product_id, changed=changed)


@router.post(
    "/repair-context/comment-draft",
    response_model=BotRepairDraftResponse,
    operation_id="build_internal_bot_repair_comment_draft_v1",
)
async def build_repair_comment_draft(
    payload: BotRepairDraftRequest,
    session: AsyncSession = Depends(get_session),
) -> BotRepairDraftResponse:
    try:
        draft = await BotRepairContextApiService.build_comment_draft(
            session,
            telegram_id=payload.telegram_id,
            order_id=payload.order_id,
            comment=payload.comment or "",
        )
    except (BotUseCaseAccessDeniedError, LookupError, ValueError) as exc:
        _raise_use_case_error(exc)
    return BotRepairDraftResponse(draft=draft)


@router.post(
    "/repair-context/preset-draft",
    response_model=BotRepairDraftResponse,
    operation_id="build_internal_bot_repair_preset_draft_v1",
)
async def build_repair_preset_draft(
    payload: BotRepairDraftRequest,
    session: AsyncSession = Depends(get_session),
) -> BotRepairDraftResponse:
    try:
        draft = await BotRepairContextApiService.build_preset_draft(
            session,
            telegram_id=payload.telegram_id,
            order_id=payload.order_id,
            fault_type=payload.fault_type or "",
        )
    except (BotUseCaseAccessDeniedError, LookupError, ValueError) as exc:
        _raise_use_case_error(exc)
    return BotRepairDraftResponse(draft=draft)


@router.post(
    "/repair-context/apply",
    response_model=BotRepairApplyResponse,
    operation_id="apply_internal_bot_repair_context_v1",
)
async def apply_repair_context(
    payload: BotRepairApplyRequest,
    session: AsyncSession = Depends(get_session),
) -> BotRepairApplyResponse:
    try:
        result = await BotRepairContextApiService.apply_comment(
            session,
            telegram_id=payload.telegram_id,
            order_id=payload.order_id,
            repair_meta_draft=payload.repair_meta_draft,
            raw_comment=payload.raw_comment,
            telegram_chat_id=payload.telegram_chat_id,
            telegram_message_id=payload.telegram_message_id,
        )
    except (BotUseCaseAccessDeniedError, LookupError, ValueError) as exc:
        _raise_use_case_error(exc)
    return BotRepairApplyResponse(result=result)
