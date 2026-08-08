from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    IntegrationOutboxEvent,
)
from services.communications.delivery_attempt_service import (
    CommunicationDeliveryAttemptService,
)
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.delivery_retry_policy import (
    delivery_retry_delay_seconds,
)


@dataclass(frozen=True)
class ExpiredLeaseRecoveryResult:
    retry_count: int
    dead_count: int


async def recover_expired_delivery_leases(
    session: AsyncSession,
    *,
    scope: CommunicationProcessingScope,
    channel: str,
    recovered_at: datetime,
    limit: int,
) -> ExpiredLeaseRecoveryResult:
    """Recover only with evidence about whether provider I/O may have begun."""

    statement = (
        select(CommunicationDelivery)
        .join(
            IntegrationOutboxEvent,
            IntegrationOutboxEvent.event_id == CommunicationDelivery.event_id,
        )
        .where(
            CommunicationDelivery.channel == channel,
            CommunicationDelivery.status == "running",
            CommunicationDelivery.lease_expires_at.is_not(None),
            CommunicationDelivery.lease_expires_at <= recovered_at,
            CommunicationDelivery.template_key.in_(
                scope.delivery_template_keys
            ),
            IntegrationOutboxEvent.event_type.in_(scope.outbox_event_types),
            IntegrationOutboxEvent.status == "published",
        )
        .order_by(
            CommunicationDelivery.lease_expires_at.asc(),
            CommunicationDelivery.created_at.asc(),
            CommunicationDelivery.delivery_id.asc(),
        )
        .limit(limit)
    )
    if scope.exact_event_id is not None:
        statement = statement.where(
            CommunicationDelivery.event_id == scope.exact_event_id
        )
    if scope.website_canary_target is not None:
        statement = statement.where(
            CommunicationDelivery.recipient_key
            == scope.website_canary_target.recipient_key
        )
    if scope.event_created_at_watermark is not None:
        statement = statement.where(
            IntegrationOutboxEvent.created_at
            >= scope.event_created_at_watermark
        )
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update(
            of=CommunicationDelivery,
            skip_locked=True,
        )

    deliveries = list((await session.execute(statement)).scalars().all())
    retry_count = 0
    dead_count = 0
    for delivery in deliveries:
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery.delivery_id, int(delivery.attempts)),
        )
        if (
            attempt is None
            or attempt.outcome != "running"
            or attempt.finished_at is not None
        ):
            # The attempt service raises a fixed state error below. Keeping this
            # branch explicit avoids guessing a provider boundary from damage.
            provider_started = True
        else:
            provider_started = (
                attempt.provider_started_at is not None
                # Rolling compatibility: an old API can hand a staff-bot
                # claim to the remote process after this migration but before
                # it learns to persist the marker. Remote handoff itself is
                # always an ambiguity boundary.
                or scope.mode == "staff_bot"
            )

        ambiguous_history_count = int(
            (
                await session.scalar(
                    select(
                        func.count(CommunicationDeliveryAttempt.attempt_no)
                    ).where(
                        CommunicationDeliveryAttempt.delivery_id
                        == delivery.delivery_id,
                        CommunicationDeliveryAttempt.ambiguous.is_(True),
                    )
                )
            )
            or 0
        )
        ambiguous = provider_started or ambiguous_history_count > 0
        exhausted = int(delivery.attempts) >= int(delivery.max_attempts)
        outcome = "dead" if ambiguous or exhausted else "retry"
        error_code = (
            "lease_expired_after_provider"
            if ambiguous
            else "lease_expired_before_provider"
        )

        await CommunicationDeliveryAttemptService.finish(
            session,
            delivery=delivery,
            finished_at=recovered_at,
            outcome=outcome,
            error_category="lease",
            error_code=error_code,
            ambiguous=ambiguous,
        )
        delivery.worker_id = None
        delivery.lease_token = None
        delivery.lease_expires_at = None
        delivery.last_error_category = "lease"
        delivery.last_error_code = error_code
        delivery.updated_at = recovered_at
        delivery.provider_message_id = None
        delivery.sent_at = None
        if outcome == "retry":
            delivery.status = "retry"
            delivery.available_at = recovered_at + timedelta(
                seconds=delivery_retry_delay_seconds(
                    delivery_id=delivery.delivery_id,
                    attempts=delivery.attempts,
                )
            )
            delivery.finished_at = None
            delivery.last_error_message = (
                "Delivery lease expired before provider call"
            )
            retry_count += 1
        else:
            delivery.status = "dead"
            delivery.finished_at = recovered_at
            delivery.last_error_message = (
                "Delivery lease expired after provider boundary"
                if ambiguous
                else "Delivery attempts exhausted before provider call"
            )
            dead_count += 1
        session.add(delivery)

    await session.flush()
    return ExpiredLeaseRecoveryResult(
        retry_count=retry_count,
        dead_count=dead_count,
    )
