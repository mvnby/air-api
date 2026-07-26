from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    IntegrationOutboxEvent,
)
import services.communications.backlog_reconciliation as backlog_module
from scripts import reconcile_installation_estimate_backlog as backlog_cli
from services.communications.backlog_reconciliation import (
    InstallationEstimateBacklogExecutionBlocked,
    InstallationEstimateBacklogReconciliation,
)
from services.communications.runtime_config import CommunicationRuntimeConfig
from services.communications.template_registry import (
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    INSTALLATION_ESTIMATE_TEMPLATE_KEY,
)


@pytest.fixture
async def backlog_session_factory(tmp_path):
    database_path = tmp_path / "communications-backlog.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _event(
    sequence: int,
    *,
    event_type: str = INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    status: str = "pending",
    created_at: datetime,
) -> IntegrationOutboxEvent:
    return IntegrationOutboxEvent(
        event_id=f"{sequence:032x}",
        event_type=event_type,
        schema_version=1,
        aggregate_type="order",
        aggregate_id=str(sequence),
        aggregate_version=1,
        deduplication_key=f"backlog-test:{sequence}",
        payload={
            "order_id": sequence,
            "status": "new_lead",
            "name": "Секретное имя",
            "phone": "+375291112233",
            "email": "private@example.com",
            "attachment_count": 1,
            "photo_categories": ["Внутренний блок"],
        },
        status=status,
        available_at=created_at,
        occurred_at=created_at,
        created_at=created_at,
        updated_at=created_at,
        published_at=created_at if status == "published" else None,
    )


def _delivery(
    sequence: int,
    *,
    event: IntegrationOutboxEvent,
    status: str,
    now: datetime,
) -> CommunicationDelivery:
    running = status == "running"
    retry = status == "retry"
    return CommunicationDelivery(
        delivery_id=f"{sequence + 10_000:032x}",
        event_id=event.event_id,
        channel="telegram",
        recipient_key=f"staff:{sequence}",
        destination="123456789",
        template_key=INSTALLATION_ESTIMATE_TEMPLATE_KEY,
        template_version=1,
        render_context={"name": "Секретное имя"},
        status=status,
        priority=20,
        attempts=1 if running or retry else 0,
        max_attempts=8,
        available_at=now,
        worker_id="stale-worker" if running else None,
        lease_token="x" * 40 if running else None,
        lease_expires_at=now - timedelta(minutes=1) if running else None,
        created_at=now,
        updated_at=now,
    )


def test_cli_requires_cutoff_and_limit_and_defaults_to_dry_run():
    parser = backlog_cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--cutoff", "2026-07-01T00:00:00Z"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--limit", "10"])

    args = parser.parse_args(
        ["--cutoff", "2026-07-01T00:00:00Z", "--limit", "10"]
    )
    assert args.execute is False
    assert args.cutoff.tzinfo is not None
    assert args.limit == 10


def test_cli_failure_output_never_exposes_arbitrary_exception_data(
    monkeypatch,
    capsys,
):
    async def fail(**_kwargs):
        raise RuntimeError(
            "postgresql://private-user:private-password@private-host/private-db"
        )

    monkeypatch.setattr(backlog_cli, "run_command", fail)
    result = backlog_cli.main(
        ["--cutoff", "2026-07-01T00:00:00Z", "--limit", "10"]
    )

    assert result == 1
    output = capsys.readouterr().out
    assert "private" not in output
    assert json.loads(output) == {
        "ok": False,
        "error_code": "installation_estimate_backlog_command_failed",
    }


@pytest.mark.asyncio
async def test_dry_run_inventories_pending_and_materialized_backlog_without_pii(
    backlog_session_factory,
):
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    cutoff = now - timedelta(days=2)
    pending = _event(1, created_at=now - timedelta(days=5))
    published = _event(
        2,
        status="published",
        created_at=now - timedelta(days=5),
    )
    processing = _event(
        3,
        status="processing",
        created_at=now - timedelta(days=5),
    )
    queued = _delivery(2, event=published, status="queued", now=now)
    running = _delivery(3, event=processing, status="running", now=now)
    async with backlog_session_factory() as session:
        session.add_all([pending, published, processing, queued, running])
        session.add(
            CommunicationDeliveryAttempt(
                delivery_id=running.delivery_id,
                attempt_no=1,
                started_at=now - timedelta(minutes=2),
                outcome="running",
            )
        )
        await session.commit()

    report = await backlog_cli.run_command(
        cutoff=cutoff,
        limit=10,
        session_factory=backlog_session_factory,
        now=now,
    )

    assert report["mode"] == "dry_run"
    assert report["candidate_total"] == 3
    assert report["pending_candidate_count"] == 1
    assert report["materialized_candidate_count"] == 2
    assert report["nonterminal_delivery_count"] == 2
    assert report["would_suppress_count"] == 3
    assert report["suppressed_count"] == 0
    assert report["activation_safe"] is False
    serialized = json.dumps(report, ensure_ascii=False)
    for secret in (
        "Секретное имя",
        "+375291112233",
        "private@example.com",
        "123456789",
        pending.event_id,
    ):
        assert secret not in serialized

    async with backlog_session_factory() as session:
        stored = await session.get(IntegrationOutboxEvent, pending.event_id)
        assert stored is not None and stored.status == "pending"
        stored_delivery = await session.get(
            CommunicationDelivery,
            queued.delivery_id,
        )
        assert stored_delivery is not None
        assert stored_delivery.status == "queued"


@pytest.mark.asyncio
async def test_execute_rejects_non_postgresql_without_mutation(
    backlog_session_factory,
):
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    event = _event(11, created_at=now - timedelta(days=5))
    async with backlog_session_factory() as session:
        session.add(event)
        await session.commit()

    with pytest.raises(
        InstallationEstimateBacklogExecutionBlocked,
        match="communications_runtime_lock_unavailable",
    ):
        await backlog_cli.run_command(
            cutoff=now - timedelta(days=2),
            limit=10,
            execute=True,
            session_factory=backlog_session_factory,
            now=now,
        )

    async with backlog_session_factory() as session:
        stored = await session.get(IntegrationOutboxEvent, event.event_id)
        assert stored is not None
        assert stored.status == "pending"
        assert stored.last_error_code is None


@pytest.mark.asyncio
async def test_execute_preflight_rejects_enabled_deployment_gate(
    backlog_session_factory,
    monkeypatch,
):
    config = replace(
        CommunicationRuntimeConfig.from_settings(),
        enabled=False,
        allow_all_mode=True,
    )
    monkeypatch.setattr(
        CommunicationRuntimeConfig,
        "from_settings",
        classmethod(lambda _cls: config),
    )
    async with backlog_session_factory() as session:
        with pytest.raises(
            InstallationEstimateBacklogExecutionBlocked,
            match="communications_runtime_deployment_gate_enabled",
        ):
            await InstallationEstimateBacklogReconciliation._assert_execution_preflight(
                session,
                runtime_lock=None,
                app_role="primary",
            )


@pytest.mark.asyncio
async def test_dry_run_reports_fail_closed_candidate_conflicts(
    backlog_session_factory,
):
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    cutoff = now - timedelta(days=2)
    owned_event = _event(21, created_at=now - timedelta(days=5))
    owned_event.worker_id = "unexpected-owner"
    malformed_event = _event(
        22,
        status="published",
        created_at=now - timedelta(days=5),
    )
    malformed_delivery = _delivery(
        22,
        event=malformed_event,
        status="queued",
        now=now,
    )
    malformed_delivery.template_key = "telegram.unexpected"

    async with backlog_session_factory() as session:
        session.add_all([owned_event, malformed_event, malformed_delivery])
        await session.commit()

    report = await backlog_cli.run_command(
        cutoff=cutoff,
        limit=10,
        session_factory=backlog_session_factory,
        now=now,
    )

    assert report["candidate_total"] == 2
    assert report["would_suppress_count"] == 0
    assert report["delivery_conflict_count"] == 1
    assert report["ownership_conflict_count"] == 1
    assert report["activation_safe"] is False


@pytest.mark.asyncio
async def test_dry_run_rejects_inconsistent_prior_attempt_history(
    backlog_session_factory,
):
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    event = _event(
        25,
        status="published",
        created_at=now - timedelta(days=5),
    )
    delivery = _delivery(25, event=event, status="retry", now=now)
    delivery.attempts = 2
    async with backlog_session_factory() as session:
        session.add_all(
            [
                event,
                delivery,
                CommunicationDeliveryAttempt(
                    delivery_id=delivery.delivery_id,
                    attempt_no=1,
                    started_at=now - timedelta(minutes=3),
                    outcome="running",
                ),
                CommunicationDeliveryAttempt(
                    delivery_id=delivery.delivery_id,
                    attempt_no=2,
                    started_at=now - timedelta(minutes=2),
                    finished_at=now - timedelta(minutes=1),
                    outcome="retry",
                    error_category="network",
                    error_code="delivery_failed",
                ),
            ]
        )
        await session.commit()

    report = await backlog_cli.run_command(
        cutoff=now - timedelta(days=2),
        limit=10,
        session_factory=backlog_session_factory,
        now=now,
    )

    assert report["candidate_total"] == 1
    assert report["would_suppress_count"] == 0
    assert report["delivery_conflict_count"] == 1
    assert report["activation_safe"] is False


@pytest.mark.asyncio
async def test_dry_run_rejects_huge_attempt_counter_without_allocating_history(
    backlog_session_factory,
):
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    event = _event(
        251,
        status="published",
        created_at=now - timedelta(days=5),
    )
    delivery = _delivery(251, event=event, status="retry", now=now)
    delivery.attempts = 1_000_000_000
    delivery.max_attempts = 1_000_000_001
    async with backlog_session_factory() as session:
        session.add_all([event, delivery])
        await session.commit()

    report = await backlog_cli.run_command(
        cutoff=now - timedelta(days=2),
        limit=10,
        session_factory=backlog_session_factory,
        now=now,
    )

    assert report["candidate_total"] == 1
    assert report["would_suppress_count"] == 0
    assert report["delivery_conflict_count"] == 1
    assert report["activation_safe"] is False


@pytest.mark.asyncio
async def test_dry_run_fails_closed_before_unbounded_delivery_load(
    backlog_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        backlog_module,
        "MAX_RECONCILIATION_DELIVERIES",
        1,
    )
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    event = _event(
        26,
        status="published",
        created_at=now - timedelta(days=5),
    )
    async with backlog_session_factory() as session:
        session.add_all(
            [
                event,
                _delivery(26, event=event, status="queued", now=now),
                _delivery(27, event=event, status="queued", now=now),
            ]
        )
        await session.commit()

    report = await backlog_cli.run_command(
        cutoff=now - timedelta(days=2),
        limit=10,
        session_factory=backlog_session_factory,
        now=now,
    )

    assert report["candidate_total"] == 1
    assert report["would_suppress_count"] == 0
    assert report["inventory_overflow_count"] == 1
    assert report["activation_safe"] is False


@pytest.mark.asyncio
async def test_dry_run_limit_is_bounded(backlog_session_factory):
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    cutoff = now - timedelta(days=2)
    async with backlog_session_factory() as session:
        session.add_all(
            [
                _event(31, created_at=now - timedelta(days=7)),
                _event(32, created_at=now - timedelta(days=6)),
                _event(33, created_at=now - timedelta(days=5)),
            ]
        )
        await session.commit()

    report = await backlog_cli.run_command(
        cutoff=cutoff,
        limit=2,
        session_factory=backlog_session_factory,
        now=now,
    )

    assert report["candidate_total"] == 3
    assert report["selected_count"] == 2
    assert report["suppressed_count"] == 0
    assert report["remaining_candidate_count"] == 3
    assert report["truncated"] is True


def test_reconciliation_rejects_future_cutoff_and_unbounded_limit():
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="cutoff"):
        InstallationEstimateBacklogReconciliation._normalize_cutoff(
            now + timedelta(minutes=1),
            now=now,
        )
    with pytest.raises(ValueError, match="limit"):
        InstallationEstimateBacklogReconciliation._validate_limit(1001)
