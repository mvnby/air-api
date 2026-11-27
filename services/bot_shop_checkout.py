from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot_shop_actions import BotShopOfferRequest, BotShopOfferResponse, BotShopOrderRequest
from api_contracts.personal_offers import (
    PersonalOfferDraftInput, PersonalOfferInstallationInput, PersonalOfferOptionInput,
    PersonalOfferPublishInput, PersonalOfferRoomInput,
)
from core.command_actor import CommandActor
from models.tenancy import TenantScope, utc_now
from services.authenticated_command_service import AuthenticatedCommandService
from services.product_collection_catalog_access import ProductCollectionCatalogAccess
from services.public_write_idempotency_service import PublicWriteCommandResponse
from services.catalog_decision_quick_order_service import CatalogDecisionQuickOrderService
from services.personal_offer_service import PersonalOfferService


async def create_shop_order(
    session: AsyncSession, scope: TenantScope, staff_id: int, request: BotShopOrderRequest,
) -> int:
    quantities = {line.product_id: line.quantity for line in request.items}
    order = await CatalogDecisionQuickOrderService.create(
        session, tenant_scope=scope, product_ids=list(quantities), quantities=quantities,
        idempotency_key=f"telegram:{staff_id}:{request.idempotency_key}",
        creator_staff_user_id=staff_id, prospect_type=request.prospect_type, proposal_mode=request.proposal_mode,
    )
    return int(order["id"])


class _OfferReceipt(BaseModel):
    offer_id: int


async def publish_shop_offer(
    session: AsyncSession, actor: CommandActor, request: BotShopOfferRequest,
) -> BotShopOfferResponse:
    scope = actor.tenant_scope

    async def publish():
        ids = [line.product_id for line in request.items]
        products = await ProductCollectionCatalogAccess.visible_by_ids(session, tenant_scope=scope, product_ids=ids)
        if len(products) != len(ids):
            raise HTTPException(422, "Часть оборудования больше недоступна. Обновите подбор.")
        options = []
        for line in request.items:
            price = Decimal(str(products[line.product_id].price))
            if price <= 0:
                raise HTTPException(422, "Для предложения по ссылке нужна розничная цена каждой модели.")
            note = f"{line.quantity} шт. на сумму {price * line.quantity} руб." if line.quantity > 1 else None
            options.append(PersonalOfferOptionInput(product_id=line.product_id, price_byn=price, note=note))
        rooms = [
            PersonalOfferRoomInput(
                title="Подобранные модели" if len(options) <= 24 else f"Модели {offset + 1}–{min(offset + 24, len(options))}",
                installation=PersonalOfferInstallationInput(mode="none"), options=options[offset:offset + 24],
            ) for offset in range(0, len(options), 24)
        ]
        try:
            draft = await PersonalOfferService.create(session, scope, PersonalOfferDraftInput(
                title=request.title[:100], expires_at=utc_now() + timedelta(days=7), rooms=rooms,
            ))
            await PersonalOfferService.publish(session, draft.id, scope, PersonalOfferPublishInput(
                expected_version=draft.version, request_id=request.request_id,
            ))
        except HTTPException as exc:
            if exc.status_code == 409:
                raise HTTPException(422, exc.detail) from exc
            raise
        # Keep public bearer URLs out of the command receipt and audit.
        return PublicWriteCommandResponse(value=_OfferReceipt(offer_id=draft.id), resource_type="personal_offer", resource_id=draft.id)

    receipt = await AuthenticatedCommandService.execute(
        session, actor=actor, command_name="telegram.shop.publish_offer", idempotency_key=str(request.request_id),
        payload=request.model_dump(include={"items", "title"}), response_model=_OfferReceipt, operation=publish,
    )
    offer_id = receipt.value.offer_id
    published = await PersonalOfferService.published_for_request(session, offer_id, scope, str(request.request_id))
    if published is None:
        raise HTTPException(422, "Ссылка больше не действует. Создайте новый подбор.")
    return BotShopOfferResponse(url=published.url, expires_at=published.expires_at)
