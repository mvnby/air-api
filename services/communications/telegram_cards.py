"""Prepare Telegram card parameters before crossing the provider boundary."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from models import CommunicationDelivery, IntegrationOutboxEvent
from services.communications.contracts import CommunicationTemplatePlanV1
from services.communications.delivery_materializer import CommunicationDeliveryMaterializer
from services.communications.delivery_service import ClaimedCommunicationDelivery
from services.communications.incoming_contracts import (
    TENANT_INCOMING_CREATED_EVENT, TENDER_REVIEW_VERSION, TenantIncomingCreatedPayloadV1,
)
from services.communications.incoming_events import tender_event_id
from services.communications.providers.base import TelegramMessageOptions
from services.communications.templates.incoming import manager_incoming_url, render_tenant_incoming_v1, tender_heading
from services.communications.templates.website import _escape_bounded


class TenderCardPending(Exception):
    """An earlier revision of the card still has a pending delivery."""


class TenderCardUnavailable(Exception):
    """A silent update needs a previously sent card for this recipient."""


async def _previous_delivery(session, claim, event):
    delivery_id = CommunicationDeliveryMaterializer.build_delivery_id(
        event_id=event.event_id, channel=claim.channel, recipient_key=claim.recipient_key,
        template_version=claim.template_version,
    )
    delivery = await session.get(CommunicationDelivery, delivery_id)
    if delivery is None:
        if event.status in {"pending", "processing"}:
            raise TenderCardPending
    elif delivery.destination == claim.destination:
        if delivery.status in {"queued", "retry", "running"}:
            raise TenderCardPending
        return delivery
    return None


async def incoming_card(
    session: AsyncSession, claim: ClaimedCommunicationDelivery, plan: CommunicationTemplatePlanV1,
) -> tuple[str, TelegramMessageOptions]:
    payload = TenantIncomingCreatedPayloadV1.model_validate(plan.render_context)
    card = payload.tender
    buttons = [("Открыть в Manager", manager_incoming_url(payload.entity_type, payload.entity_id))]
    if card and card.source_url:
        buttons.append(("На площадку", card.source_url))

    edit_id = None
    alert = None
    edit_only = False
    if card and card.prior_event_id:
        previous = await session.get(IntegrationOutboxEvent, card.prior_event_id)
        if (previous is None or previous.event_type != TENANT_INCOMING_CREATED_EVENT
                or previous.aggregate_type != payload.entity_type or previous.aggregate_id != str(payload.entity_id)
                or previous.aggregate_version != 1 or previous.payload.get("tenant_id") != payload.tenant_id
                or previous.payload.get("storefront_id") != payload.storefront_id):
            raise ValueError("Original tender card does not match its update")
        delivery = await _previous_delivery(session, claim, previous)
        if delivery and delivery.status == "sent" and (delivery.provider_message_id or "").isdigit():
            edit_id = int(delivery.provider_message_id)
        if card.status == "review":
            edit_only = True
            if not edit_id:
                raise TenderCardUnavailable
        else:
            # Finish the silent edit before the recommendation can edit the same message.
            review = await session.get(IntegrationOutboxEvent, tender_event_id(payload.entity_id, TENDER_REVIEW_VERSION))
            if review is not None:
                await _previous_delivery(session, claim, review)
            if edit_id:
                title = _escape_bounded(tender_heading(card.title), max_length=146)
                alert = f"<b>Можно рассмотреть тендер №{payload.entity_id}</b>\n{title}"

    silent = bool(card and (card.status != "recommend" or (
        card.deadline_at and card.deadline_at <= datetime.now(timezone.utc)
    )))
    return render_tenant_incoming_v1(plan.render_context, text_link=False), TelegramMessageOptions(
        buttons=tuple(buttons), silent=silent, tender_topic=card is not None,
        edit_message_id=edit_id, alert_text=alert, edit_only=edit_only,
    )


def site_contact_options(plan: CommunicationTemplatePlanV1) -> TelegramMessageOptions:
    return TelegramMessageOptions(buttons=((
        "Открыть в Manager", manager_incoming_url("lead", plan.render_context["lead_id"]),
    ),))
