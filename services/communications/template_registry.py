from __future__ import annotations

from pydantic import ValidationError

from models import IntegrationOutboxEvent
from services.communications.contracts import (
    CommunicationTemplatePlanV1,
    PublicContactLeadCreatedPayloadV1,
    PublicOrderCreatedPayloadV1,
)
from services.communications.templates.website import (
    render_website_contact_lead_v1,
    render_website_order_v1,
)


PUBLIC_ORDER_CREATED_EVENT = "crm.public_order.created"
PUBLIC_CONTACT_LEAD_CREATED_EVENT = "crm.public_contact_lead.created"
CONSUMER_NAME = "communications.management_telegram"
HANDLER_VERSION = 1
SUPPORTED_EVENT_TYPES = {
    PUBLIC_ORDER_CREATED_EVENT,
    PUBLIC_CONTACT_LEAD_CREATED_EVENT,
}

ORDER_TEMPLATE_KEY = "telegram.website_order_created"
CONTACT_LEAD_TEMPLATE_KEY = "telegram.website_contact_lead_created"


class UnsupportedCommunicationEvent(ValueError):
    pass


class InvalidCommunicationEventPayload(ValueError):
    pass


class WebsiteTemplateRegistry:
    @staticmethod
    def plan(event: IntegrationOutboxEvent) -> CommunicationTemplatePlanV1:
        if event.schema_version != 1:
            raise UnsupportedCommunicationEvent(
                f"Unsupported schema version {event.schema_version} for {event.event_type}"
            )
        try:
            if event.event_type == PUBLIC_ORDER_CREATED_EVENT:
                payload = PublicOrderCreatedPayloadV1.model_validate(event.payload)
                template_key = ORDER_TEMPLATE_KEY
            elif event.event_type == PUBLIC_CONTACT_LEAD_CREATED_EVENT:
                payload = PublicContactLeadCreatedPayloadV1.model_validate(event.payload)
                template_key = CONTACT_LEAD_TEMPLATE_KEY
            else:
                raise UnsupportedCommunicationEvent(
                    f"Unsupported communication event {event.event_type!r}"
                )
        except ValidationError as exc:
            raise InvalidCommunicationEventPayload(
                f"Invalid payload for {event.event_type} schema v{event.schema_version}"
            ) from exc

        return CommunicationTemplatePlanV1(
            template_key=template_key,
            render_context=payload.model_dump(mode="json"),
        )

    @staticmethod
    def render(plan: CommunicationTemplatePlanV1) -> str:
        if plan.template_version != 1:
            raise UnsupportedCommunicationEvent(
                f"Unsupported template version {plan.template_version}"
            )
        if plan.template_key == ORDER_TEMPLATE_KEY:
            return render_website_order_v1(plan.render_context)
        if plan.template_key == CONTACT_LEAD_TEMPLATE_KEY:
            return render_website_contact_lead_v1(plan.render_context)
        raise UnsupportedCommunicationEvent(
            f"Unsupported communication template {plan.template_key!r}"
        )
