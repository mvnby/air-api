from datetime import datetime, timedelta, timezone

import pytest

from models import CommunicationDelivery, CommunicationDeliveryAttempt
from scripts.communications_installation_notifications import run_command
from services.communications.installation_notifications import (
    InstallationNotificationControlRejected,
)
from services.communications.template_registry import (
    INSTALLATION_ESTIMATE_TEMPLATE_KEY,
)
from tests.unit.test_communications_installation_notifications_command import (
    _event,
    _runtime_config,
    _seed_dormant_runtime,
    _terminal_delivery,
    allow_sqlite_operator_checks,
    operator_session_factory,
)


@pytest.mark.asyncio
async def test_activation_counts_future_skewed_unsafe_rows_fail_closed(
    operator_session_factory,
    allow_sqlite_operator_checks,
):
    await _seed_dormant_runtime(operator_session_factory)
    future = datetime.now(timezone.utc) + timedelta(days=1)
    pending = _event(51, status="pending", created_at=future)
    running_event = _event(52, status="published", created_at=future)
    ambiguous_event = _event(53, status="published", created_at=future)
    running = CommunicationDelivery(
        delivery_id=f"{251:032x}",
        event_id=running_event.event_id,
        channel="telegram",
        recipient_key="staff:owner",
        destination="90001",
        template_key=INSTALLATION_ESTIMATE_TEMPLATE_KEY,
        template_version=1,
        render_context={},
        status="running",
        attempts=1,
        max_attempts=3,
        available_at=future,
        worker_id="future-worker",
        lease_token="x" * 43,
        lease_expires_at=future + timedelta(minutes=1),
        created_at=future,
        updated_at=future,
    )
    ambiguous = _terminal_delivery(
        53,
        event_id=ambiguous_event.event_id,
        status="dead",
        now=future,
    )
    ambiguous.status = "retry"
    ambiguous.finished_at = None
    async with operator_session_factory() as session:
        session.add_all(
            [
                pending,
                running_event,
                ambiguous_event,
                running,
                ambiguous,
                CommunicationDeliveryAttempt(
                    delivery_id=running.delivery_id,
                    attempt_no=1,
                    started_at=future,
                    outcome="running",
                ),
                CommunicationDeliveryAttempt(
                    delivery_id=ambiguous.delivery_id,
                    attempt_no=1,
                    started_at=future,
                    finished_at=future,
                    outcome="retry",
                    error_category="provider",
                    error_code="provider_ack_unknown",
                    ambiguous=True,
                ),
            ]
        )
        await session.commit()

    plan = await run_command(
        "plan",
        session_factory=operator_session_factory,
        config=_runtime_config(),
        bot_token="valid-token",
        runtime_locks_enabled=True,
    )
    assert plan["backlog_count"] == 3
    assert plan["running_count"] == 1
    assert plan["ambiguous_nonterminal_count"] == 1
    assert plan["ambiguous_terminal_count"] == 0
    assert plan["ambiguous_total_count"] == 1
    assert "installation_backlog_not_reconciled" in plan["blockers"]
    assert "installation_delivery_running" in plan["blockers"]
    assert "installation_ambiguous_outcomes_unreconciled" in plan["blockers"]

    with pytest.raises(
        InstallationNotificationControlRejected,
        match="installation_backlog_not_reconciled",
    ):
        await run_command(
            "enable",
            session_factory=operator_session_factory,
            config=_runtime_config(),
            bot_token="valid-token",
            runtime_locks_enabled=True,
        )
