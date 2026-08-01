from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    ConsumerInbox,
    IntegrationOutboxEvent,
)
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.contracts import CommunicationTemplatePlanV1
from services.communications.delivery_materializer import (
    CommunicationDeliveryMaterializer,
)
from services.communications.recipient_directory import (
    TenantWebsiteManagementRecipientDirectory,
)
from services.communications.provider_boundary_authorization import (
    WebsiteCanaryProviderBoundaryRejected,
    lock_exact_website_recipient,
)
from services.communications.template_registry import (
    CONSUMER_NAME,
    HANDLER_VERSION,
    UnsupportedCommunicationEvent,
    WebsiteTemplateRegistry,
)
from services.communications.templates import TemplateRenderError
from services.communications.website_canary_target import (
    WebsiteCanaryScopeMismatch,
    WebsiteCanaryTarget,
)


TerminalOutcome = Literal["sent", "dead", "canceled", "ambiguous", "aborted"]


class WebsiteCanaryEvidenceRejected(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


@dataclass(frozen=True)
class WebsiteCanaryEvidence:
    event: IntegrationOutboxEvent
    delivery: CommunicationDelivery | None
    latest_attempt: CommunicationDeliveryAttempt | None
    ambiguous_attempt_count: int
    render_context_fingerprint: str | None = None


def render_context_fingerprint(value: dict) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _locked(statement, session: AsyncSession, *, lock: bool):
    if lock and session.get_bind().dialect.name == "postgresql":
        return statement.with_for_update()
    return statement


async def load_target_event(
    session: AsyncSession,
    *,
    target: WebsiteCanaryTarget,
    lock: bool,
) -> tuple[IntegrationOutboxEvent, CommunicationTemplatePlanV1]:
    event = await session.get(
        IntegrationOutboxEvent,
        target.event_id,
        populate_existing=lock,
        with_for_update=(lock and session.get_bind().dialect.name == "postgresql"),
    )
    if event is None:
        raise WebsiteCanaryEvidenceRejected("website_canary_event_not_found")
    try:
        plan = WebsiteTemplateRegistry.plan(event)
        WebsiteTemplateRegistry.render(plan)
        target.assert_event_plan(
            event_id=event.event_id,
            event_type=event.event_type,
            template_key=plan.template_key,
            audience=plan.audience,
            render_context=plan.render_context,
        )
    except (
        TemplateRenderError,
        UnsupportedCommunicationEvent,
        WebsiteCanaryScopeMismatch,
        ValueError,
    ):
        raise WebsiteCanaryEvidenceRejected(
            "website_canary_event_scope_invalid"
        ) from None
    return event, plan


async def _current_destination(
    session: AsyncSession,
    *,
    target: WebsiteCanaryTarget,
) -> str:
    try:
        locked_destination = await lock_exact_website_recipient(
            session,
            target=target,
        )
        recipients = await TenantWebsiteManagementRecipientDirectory.list_telegram(
            session,
            tenant_id=target.tenant_id,
            storefront_id=target.storefront_id,
        )
    except (
        CommunicationsCanarySafetyError,
        WebsiteCanaryProviderBoundaryRejected,
    ) as error:
        raise WebsiteCanaryEvidenceRejected(error.error_code) from None
    matches = [
        recipient
        for recipient in recipients
        if recipient.recipient_key == target.recipient_key
    ]
    if len(matches) != 1:
        raise WebsiteCanaryEvidenceRejected(
            "website_canary_terminal_recipient_invalid"
        )
    if matches[0].destination != locked_destination:
        raise WebsiteCanaryEvidenceRejected(
            "website_canary_terminal_recipient_invalid"
        )
    return locked_destination


def _validate_attempts(
    *,
    delivery: CommunicationDelivery,
    attempts: list[CommunicationDeliveryAttempt],
) -> int:
    expected_numbers = list(range(1, int(delivery.attempts) + 1))
    if (
        [int(attempt.attempt_no) for attempt in attempts] != expected_numbers
        or any(attempt.delivery_id != delivery.delivery_id for attempt in attempts)
    ):
        raise WebsiteCanaryEvidenceRejected(
            "website_canary_attempt_snapshot_invalid"
        )
    ambiguous_count = sum(1 for attempt in attempts if attempt.ambiguous)
    if ambiguous_count:
        return ambiguous_count
    latest = attempts[-1] if attempts else None
    expected_latest = {
        "queued": None,
        "running": "running",
        "retry": "retry",
        "sent": "sent",
        "dead": "dead",
        "canceled": "canceled",
    }[delivery.status]
    if (
        (latest is None) != (expected_latest is None)
        or (latest is not None and latest.outcome != expected_latest)
        or any(attempt.outcome != "retry" for attempt in attempts[:-1])
        or (
            delivery.status == "sent"
            and (latest is None or latest.provider_started_at is None)
        )
    ):
        raise WebsiteCanaryEvidenceRejected(
            "website_canary_attempt_snapshot_invalid"
        )
    return 0


async def load_website_canary_evidence(
    session: AsyncSession,
    *,
    target: WebsiteCanaryTarget,
    lock: bool,
) -> WebsiteCanaryEvidence:
    event, plan = await load_target_event(
        session,
        target=target,
        lock=lock,
    )
    inbox = await session.get(
        ConsumerInbox,
        (CONSUMER_NAME, target.event_id),
        populate_existing=lock,
        with_for_update=(lock and session.get_bind().dialect.name == "postgresql"),
    )
    deliveries = list(
        (
            await session.execute(
                _locked(
                    select(CommunicationDelivery).where(
                        CommunicationDelivery.event_id == target.event_id
                    ),
                    session,
                    lock=lock,
                )
            )
        ).scalars()
    )
    if len(deliveries) > 1:
        raise WebsiteCanaryEvidenceRejected(
            "website_canary_delivery_scope_invalid"
        )
    delivery = deliveries[0] if deliveries else None
    if (inbox is None) != (delivery is None):
        raise WebsiteCanaryEvidenceRejected(
            "website_canary_materialization_inconsistent"
        )
    if delivery is None:
        if event.status == "published":
            raise WebsiteCanaryEvidenceRejected(
                "website_canary_materialization_inconsistent"
            )
        return WebsiteCanaryEvidence(event, None, None, 0)
    if (
        event.status != "published"
        or inbox is None
        or inbox.handler_version != HANDLER_VERSION
        or inbox.processed_at is None
    ):
        raise WebsiteCanaryEvidenceRejected(
            "website_canary_materialization_inconsistent"
        )

    destination = await _current_destination(session, target=target)
    expected_delivery_id = CommunicationDeliveryMaterializer.build_delivery_id(
        event_id=target.event_id,
        channel=plan.channel,
        recipient_key=target.recipient_key,
        template_version=plan.template_version,
    )
    expected_context = dict(plan.render_context)
    actual_context = dict(delivery.render_context or {})
    expected_fingerprint = render_context_fingerprint(expected_context)
    actual_fingerprint = render_context_fingerprint(actual_context)
    if (
        delivery.delivery_id != expected_delivery_id
        or delivery.event_id != target.event_id
        or delivery.channel != "telegram"
        or delivery.channel != plan.channel
        or delivery.recipient_key != target.recipient_key
        or delivery.destination != destination
        or delivery.template_key != target.template_key
        or delivery.template_key != plan.template_key
        or int(delivery.template_version) != int(plan.template_version)
        or actual_context != expected_context
        or actual_fingerprint != expected_fingerprint
        or int(delivery.max_attempts) != max(1, int(event.max_attempts))
        or int(delivery.priority) != max(0, int(event.priority))
    ):
        raise WebsiteCanaryEvidenceRejected(
            "website_canary_delivery_snapshot_invalid"
        )

    attempts = list(
        (
            await session.execute(
                _locked(
                    select(CommunicationDeliveryAttempt)
                    .where(
                        CommunicationDeliveryAttempt.delivery_id
                        == delivery.delivery_id
                    )
                    .order_by(CommunicationDeliveryAttempt.attempt_no.asc()),
                    session,
                    lock=lock,
                )
            )
        ).scalars()
    )
    ambiguous_count = _validate_attempts(
        delivery=delivery,
        attempts=attempts,
    )
    return WebsiteCanaryEvidence(
        event=event,
        delivery=delivery,
        latest_attempt=attempts[-1] if attempts else None,
        ambiguous_attempt_count=ambiguous_count,
        render_context_fingerprint=actual_fingerprint,
    )


def classify_website_canary_evidence(
    evidence: WebsiteCanaryEvidence,
) -> tuple[Literal["pending", "terminal"], TerminalOutcome | None]:
    delivery = evidence.delivery
    if evidence.ambiguous_attempt_count:
        return "terminal", "ambiguous"
    if delivery is None:
        if evidence.event.status == "dead":
            return "terminal", "dead"
        return "pending", None
    if delivery.status == "sent" and delivery.provider_message_id:
        return "terminal", "sent"
    if delivery.status == "dead":
        return "terminal", "dead"
    if delivery.status == "canceled":
        return "terminal", "canceled"
    return "pending", None
