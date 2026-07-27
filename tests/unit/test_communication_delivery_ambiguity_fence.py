from datetime import timedelta

import pytest

from models import CommunicationDeliveryAttempt
from services.communications.delivery_service import CommunicationDeliveryService
from tests.unit.test_communication_delivery_service import (
    ALL_SCOPE,
    NOW,
    _delivery,
    delivery_session_factory,
)


def _retry_attempt(
    sequence: int,
    *,
    ambiguous: bool,
) -> CommunicationDeliveryAttempt:
    return CommunicationDeliveryAttempt(
        delivery_id=f"{sequence:032x}",
        attempt_no=1,
        started_at=NOW - timedelta(seconds=2),
        finished_at=NOW - timedelta(seconds=1),
        outcome="retry",
        error_category="provider" if ambiguous else "rate_limit",
        error_code=(
            "provider_call_failed"
            if ambiguous
            else "telegram_retry_after"
        ),
        retry_after_seconds=None if ambiguous else 1,
        ambiguous=ambiguous,
    )


@pytest.mark.asyncio
async def test_claim_skips_retry_with_ambiguous_history_but_claims_retry_after(
    delivery_session_factory,
):
    async with delivery_session_factory() as session:
        session.add_all(
            [
                _delivery(81, status="retry", attempts=1, priority=1),
                _retry_attempt(81, ambiguous=True),
                _delivery(82, status="retry", attempts=1, priority=2),
                _retry_attempt(82, ambiguous=False),
            ]
        )
        await session.commit()

        claim = await CommunicationDeliveryService.claim_next(
            session,
            scope=ALL_SCOPE,
            worker_id="ambiguity-fence-worker",
            now=NOW,
        )

        assert claim is not None
        assert claim.delivery_id == f"{82:032x}"
        ambiguous_delivery = await session.get(
            type(_delivery(81)),
            f"{81:032x}",
        )
        assert ambiguous_delivery is not None
        assert ambiguous_delivery.status == "retry"
        assert ambiguous_delivery.attempts == 1


@pytest.mark.asyncio
async def test_expired_recovery_terminally_closes_ambiguous_history(
    delivery_session_factory,
):
    running = _delivery(
        83,
        status="running",
        attempts=2,
        worker_id="corrupt-worker",
        lease_token="x" * 43,
        lease_expires_at=NOW - timedelta(seconds=1),
    )
    async with delivery_session_factory() as session:
        session.add_all(
            [
                running,
                _retry_attempt(83, ambiguous=True),
                CommunicationDeliveryAttempt(
                    delivery_id=running.delivery_id,
                    attempt_no=2,
                    started_at=NOW - timedelta(seconds=1),
                    outcome="running",
                ),
            ]
        )
        await session.commit()

        result = await CommunicationDeliveryService.recover_expired_leases(
            session,
            scope=ALL_SCOPE,
            now=NOW,
        )

        assert result.retry_count == 0
        assert result.dead_count == 1
        await session.refresh(running)
        assert running.status == "dead"
        current = await session.get(
            CommunicationDeliveryAttempt,
            (running.delivery_id, 2),
        )
        assert current is not None
        assert current.outcome == "dead"
        assert current.ambiguous is True
        assert current.error_code == "lease_expired_after_provider"
