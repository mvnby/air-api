from __future__ import annotations

from collections.abc import Sequence

from models import IntegrationOutboxEvent
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.contracts import (
    CommunicationRecipientV1,
    CommunicationTemplatePlanV1,
)
from services.communications.processing_scope import CommunicationProcessingScope


def validate_scope_plan(
    *,
    scope: CommunicationProcessingScope,
    event: IntegrationOutboxEvent,
    plan: CommunicationTemplatePlanV1,
) -> None:
    target = scope.website_canary_target
    if target is None:
        return
    target.assert_event_plan(
        event_id=event.event_id,
        event_type=event.event_type,
        template_key=plan.template_key,
        audience=plan.audience,
        render_context=plan.render_context,
    )


def recipients_for_scope(
    *,
    scope: CommunicationProcessingScope,
    recipients: Sequence[CommunicationRecipientV1],
    event_id: str,
    template_key: str,
) -> list[CommunicationRecipientV1]:
    """Narrow a safe full directory to the one immutable website target."""

    target = scope.website_canary_target
    if target is None:
        return list(recipients)
    if event_id != target.event_id or template_key != target.template_key:
        raise CommunicationsCanarySafetyError(
            "website_canary_delivery_scope_changed"
        )
    matches = [
        recipient
        for recipient in recipients
        if recipient.recipient_key == target.recipient_key
    ]
    if len(matches) != 1:
        raise CommunicationsCanarySafetyError(
            "website_canary_recipient_scope_changed"
        )
    return matches


def routing_snapshot(
    recipients: Sequence[CommunicationRecipientV1],
) -> set[tuple[str, str]]:
    return {
        (recipient.recipient_key, recipient.destination)
        for recipient in recipients
    }
