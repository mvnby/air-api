from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import CommunicationDelivery, CommunicationDeliveryAttempt
from services.communications.delivery_attempt_service import (
    CommunicationDeliveryAttemptService,
)
from services.communications.delivery_retry_policy import (
    delivery_retry_delay_seconds,
)
from services.communications.delivery_service import (
    DELIVERY_STATUS_DEAD,
    DELIVERY_STATUS_RETRY,
    DELIVERY_STATUS_RUNNING,
    CommunicationDeliveryLeaseLost,
    CommunicationDeliveryNotFound,
    CommunicationDeliveryService,
    DeliveryFailureOutcome,
)


async def release_pre_provider_claim(
    session: AsyncSession,
    *,
    delivery_id: str,
    worker_id: str,
    lease_token: str,
) -> DeliveryFailureOutcome:
    """Release an exact owned claim only while provider I/O is provably absent."""

    normalized_delivery_id = CommunicationDeliveryService._normalize_delivery_id(
        delivery_id
    )
    normalized_worker_id = CommunicationDeliveryService._normalize_worker_id(
        worker_id
    )
    normalized_lease_token = CommunicationDeliveryService._normalize_lease_token(
        lease_token
    )
    statement = select(CommunicationDelivery).where(
        CommunicationDelivery.delivery_id == normalized_delivery_id,
        CommunicationDelivery.status == DELIVERY_STATUS_RUNNING,
        CommunicationDelivery.worker_id == normalized_worker_id,
        CommunicationDelivery.lease_token == normalized_lease_token,
    )
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    delivery = (await session.execute(statement)).scalar_one_or_none()
    if delivery is None:
        if await session.get(CommunicationDelivery, normalized_delivery_id) is None:
            raise CommunicationDeliveryNotFound(
                f"Communication delivery {normalized_delivery_id!r} was not found"
            )
        raise CommunicationDeliveryLeaseLost(
            f"Communication delivery {normalized_delivery_id!r} is no longer owned"
        )

    attempt_statement = select(CommunicationDeliveryAttempt).where(
        CommunicationDeliveryAttempt.delivery_id == normalized_delivery_id,
        CommunicationDeliveryAttempt.attempt_no == int(delivery.attempts),
    )
    if session.get_bind().dialect.name == "postgresql":
        attempt_statement = attempt_statement.with_for_update()
    attempt = (await session.execute(attempt_statement)).scalar_one_or_none()
    if (
        attempt is None
        or attempt.outcome != DELIVERY_STATUS_RUNNING
        or attempt.finished_at is not None
        or attempt.provider_started_at is not None
    ):
        raise CommunicationDeliveryLeaseLost(
            f"Communication delivery {normalized_delivery_id!r} "
            "cannot be released before provider"
        )

    released_at = await CommunicationDeliveryService.database_now(session)
    exhausted = int(delivery.attempts) >= int(delivery.max_attempts)
    outcome = DELIVERY_STATUS_DEAD if exhausted else DELIVERY_STATUS_RETRY
    error_code = "runtime_control_fenced_before_provider"
    await CommunicationDeliveryAttemptService.finish(
        session,
        delivery=delivery,
        finished_at=released_at,
        outcome=outcome,
        error_category="lease",
        error_code=error_code,
        ambiguous=False,
    )
    delivery.status = outcome
    delivery.worker_id = None
    delivery.lease_token = None
    delivery.lease_expires_at = None
    delivery.provider_message_id = None
    delivery.last_error_category = "lease"
    delivery.last_error_code = error_code
    delivery.last_error_message = "Runtime control fenced delivery before provider"
    delivery.sent_at = None
    delivery.finished_at = released_at if exhausted else None
    delivery.updated_at = released_at
    next_attempt_at = None
    if not exhausted:
        next_attempt_at = released_at + timedelta(
            seconds=delivery_retry_delay_seconds(
                delivery_id=delivery.delivery_id,
                attempts=delivery.attempts,
            )
        )
        delivery.available_at = next_attempt_at
    session.add(delivery)
    await session.flush()
    return DeliveryFailureOutcome(
        status=outcome,
        attempts=int(delivery.attempts),
        next_attempt_at=next_attempt_at,
    )
