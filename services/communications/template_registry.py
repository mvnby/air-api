from __future__ import annotations

from pydantic import ValidationError

from models import IntegrationOutboxEvent
from services.communications.canary_run_id import normalize_canary_run_id
from services.communications.contracts import (
    CommunicationTemplatePlanV1,
    InstallationEstimateLeadCreatedPayloadV1,
    PublicContactLeadCreatedPayloadV1,
    PublicOrderCreatedPayloadV1,
    TelegramCanaryRequestedPayloadV1,
)
from services.communications.installation_activation_fence import (
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
)
from services.communications.outbox_service import IntegrationOutboxService
from services.communications.templates.operations import render_telegram_canary_v1
from services.communications.templates.website import (
    render_installation_estimate_lead_v1,
    render_website_contact_lead_v1,
    render_website_order_v1,
)
from services.communications.staff_task_contracts import (
    STAFF_TASK_EVENT_TYPE_VALUES,
    STAFF_TASK_TEMPLATE_KEY_VALUES,
)
from services.communications.staff_task_templates import (
    plan_staff_task_event,
    render_staff_task_v1,
    validate_staff_task_template,
)


PUBLIC_ORDER_CREATED_EVENT = "crm.public_order.created"
PUBLIC_CONTACT_LEAD_CREATED_EVENT = "crm.public_contact_lead.created"
TELEGRAM_CANARY_REQUESTED_EVENT = "ops.communications.telegram_canary.requested"
TELEGRAM_CANARY_AGGREGATE_TYPE = "communications_canary"
TELEGRAM_CANARY_AGGREGATE_VERSION = 1
TELEGRAM_CANARY_IDEMPOTENCY_PREFIX = "communications-telegram-canary-v1"
TELEGRAM_CANARY_PRIORITY = 0
TELEGRAM_CANARY_MAX_ATTEMPTS = 1
CONSUMER_NAME = "communications.management_telegram"
HANDLER_VERSION = 1
SUPPORTED_EVENT_TYPES = {
    PUBLIC_ORDER_CREATED_EVENT,
    PUBLIC_CONTACT_LEAD_CREATED_EVENT,
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    TELEGRAM_CANARY_REQUESTED_EVENT,
    *STAFF_TASK_EVENT_TYPE_VALUES,
}

ORDER_TEMPLATE_KEY = "telegram.website_order_created"
CONTACT_LEAD_TEMPLATE_KEY = "telegram.website_contact_lead_created"
INSTALLATION_ESTIMATE_TEMPLATE_KEY = "telegram.installation_estimate_lead_created"
TELEGRAM_CANARY_TEMPLATE_KEY = "telegram.operations_canary"


def telegram_canary_aggregate_id(run_id: str) -> str:
    return normalize_canary_run_id(run_id)


def telegram_canary_idempotency_key(run_id: str) -> str:
    return f"{TELEGRAM_CANARY_IDEMPOTENCY_PREFIX}:{normalize_canary_run_id(run_id)}"


def telegram_canary_deduplication_key(run_id: str) -> str:
    normalized_run_id = normalize_canary_run_id(run_id)
    return IntegrationOutboxService.build_deduplication_key(
        event_type=TELEGRAM_CANARY_REQUESTED_EVENT,
        schema_version=1,
        aggregate_type=TELEGRAM_CANARY_AGGREGATE_TYPE,
        aggregate_id=normalized_run_id,
        aggregate_version=TELEGRAM_CANARY_AGGREGATE_VERSION,
        idempotency_key=telegram_canary_idempotency_key(normalized_run_id),
    )


def telegram_canary_event_id(run_id: str) -> str:
    return IntegrationOutboxService.build_event_id(
        telegram_canary_deduplication_key(run_id)
    )


class UnsupportedCommunicationEvent(ValueError):
    pass


class InvalidCommunicationEventPayload(ValueError):
    pass


class WebsiteTemplateRegistry:
    @staticmethod
    def plan_delivery(
        *,
        channel: str,
        template_key: str,
        template_version: int,
        render_context: dict,
    ) -> CommunicationTemplatePlanV1:
        if channel != "telegram":
            raise UnsupportedCommunicationEvent(
                f"Unsupported communication channel {channel!r}"
            )
        if template_version != 1:
            raise UnsupportedCommunicationEvent(
                f"Unsupported template version {template_version}"
            )

        try:
            if template_key == ORDER_TEMPLATE_KEY:
                payload = PublicOrderCreatedPayloadV1.model_validate(render_context)
                audience = "management"
            elif template_key == CONTACT_LEAD_TEMPLATE_KEY:
                payload = PublicContactLeadCreatedPayloadV1.model_validate(
                    render_context
                )
                audience = "management"
            elif template_key == INSTALLATION_ESTIMATE_TEMPLATE_KEY:
                payload = InstallationEstimateLeadCreatedPayloadV1.model_validate(
                    render_context
                )
                audience = "installation_estimate_owners"
            elif template_key == TELEGRAM_CANARY_TEMPLATE_KEY:
                payload = TelegramCanaryRequestedPayloadV1.model_validate(
                    render_context
                )
                audience = "operations_canary"
            elif template_key in STAFF_TASK_TEMPLATE_KEY_VALUES:
                try:
                    payload = validate_staff_task_template(
                        template_key=template_key,
                        render_context=render_context,
                    )
                except (ValidationError, ValueError) as exc:
                    raise InvalidCommunicationEventPayload(
                        f"Invalid render context for {template_key} v{template_version}"
                    ) from exc
                audience = "staff_assignee"
            else:
                raise UnsupportedCommunicationEvent(
                    f"Unsupported communication template {template_key!r}"
                )
        except ValidationError as exc:
            raise InvalidCommunicationEventPayload(
                f"Invalid render context for {template_key} v{template_version}"
            ) from exc

        return CommunicationTemplatePlanV1(
            channel="telegram",
            audience=audience,
            template_key=template_key,
            template_version=1,
            render_context=payload.model_dump(mode="json"),
        )

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
            elif event.event_type == INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT:
                payload = InstallationEstimateLeadCreatedPayloadV1.model_validate(
                    event.payload
                )
                template_key = INSTALLATION_ESTIMATE_TEMPLATE_KEY
            elif event.event_type == TELEGRAM_CANARY_REQUESTED_EVENT:
                payload = TelegramCanaryRequestedPayloadV1.model_validate(event.payload)
                run_id = payload.run_id
                if (
                    event.aggregate_type != TELEGRAM_CANARY_AGGREGATE_TYPE
                    or event.aggregate_id != telegram_canary_aggregate_id(run_id)
                    or event.aggregate_version != TELEGRAM_CANARY_AGGREGATE_VERSION
                    or event.idempotency_key
                    != telegram_canary_idempotency_key(run_id)
                    or event.priority != TELEGRAM_CANARY_PRIORITY
                    or event.max_attempts != TELEGRAM_CANARY_MAX_ATTEMPTS
                    or event.actor_id is not None
                    or event.correlation_id is not None
                    or event.causation_id is not None
                    or event.deduplication_key
                    != telegram_canary_deduplication_key(run_id)
                    or event.event_id != telegram_canary_event_id(run_id)
                ):
                    raise InvalidCommunicationEventPayload(
                        "Invalid fixed Telegram canary metadata"
                    )
                template_key = TELEGRAM_CANARY_TEMPLATE_KEY
            elif event.event_type in STAFF_TASK_EVENT_TYPE_VALUES:
                try:
                    template_key, payload = plan_staff_task_event(
                        event_type=event.event_type,
                        payload=event.payload,
                    )
                except (ValidationError, ValueError) as exc:
                    raise InvalidCommunicationEventPayload(
                        f"Invalid payload for {event.event_type} schema v{event.schema_version}"
                    ) from exc
            else:
                raise UnsupportedCommunicationEvent(
                    f"Unsupported communication event {event.event_type!r}"
                )
        except ValidationError as exc:
            raise InvalidCommunicationEventPayload(
                f"Invalid payload for {event.event_type} schema v{event.schema_version}"
            ) from exc

        return WebsiteTemplateRegistry.plan_delivery(
            channel="telegram",
            template_key=template_key,
            template_version=1,
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
        if plan.template_key == INSTALLATION_ESTIMATE_TEMPLATE_KEY:
            return render_installation_estimate_lead_v1(plan.render_context)
        if plan.template_key == TELEGRAM_CANARY_TEMPLATE_KEY:
            if plan.audience != "operations_canary":
                raise UnsupportedCommunicationEvent(
                    "Telegram canary template requires operations_canary audience"
                )
            return render_telegram_canary_v1(plan.render_context)
        if plan.template_key in STAFF_TASK_TEMPLATE_KEY_VALUES:
            payload = validate_staff_task_template(
                template_key=plan.template_key,
                render_context=plan.render_context,
            )
            return render_staff_task_v1(payload)
        raise UnsupportedCommunicationEvent(
            f"Unsupported communication template {plan.template_key!r}"
        )
