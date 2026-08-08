from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    CommunicationWebsiteBacklogOperation,
    IntegrationOutboxEvent,
)
from scripts import reconcile_website_communication_backlog as backlog_cli
from services.communications.backlog_reconciliation import (
    InstallationEstimateBacklogExecutionBlocked,
    InstallationEstimateBacklogReconciliation,
)
from services.communications.tenant_website_events import (
    TENANT_WEBSITE_EVENT_TEMPLATE_KEYS,
    TENANT_WEBSITE_EVENT_TYPES,
)
from services.communications.website_backlog_reconciliation import (
    WebsiteBacklogManifestItem,
    WebsiteCommunicationBacklogReconciliation,
)
from services.communications.website_backlog_operation import (
    WebsiteBacklogOperationManifestMismatch,
    WebsiteBacklogOperationRunner,
)


@pytest.fixture
async def backlog_manifest_session_factory(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'website-backlog.sqlite3'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _manifest(
    *,
    cutoff: datetime,
    counts: dict[str, int] | None = None,
    retain: set[str] | None = None,
):
    counts = counts or {}
    retain = retain or set()
    return tuple(
        WebsiteBacklogManifestItem(
            event_type=event_type,
            cutoff=cutoff,
            expected_count=counts.get(event_type, 0),
            disposition=(
                "retain" if event_type in retain else "terminal_no_send"
            ),
        )
        for event_type in TENANT_WEBSITE_EVENT_TYPES
    )


def _event(sequence: int, event_type: str, created_at: datetime):
    return IntegrationOutboxEvent(
        event_id=f"{sequence:032x}",
        event_type=event_type,
        schema_version=1,
        aggregate_type="website",
        aggregate_id=str(sequence),
        aggregate_version=1,
        deduplication_key=f"website-backlog:{sequence}",
        payload={"private": "never reported"},
        status="published",
        attempts=1,
        available_at=created_at,
        occurred_at=created_at,
        published_at=created_at,
        created_at=created_at,
        updated_at=created_at,
    )


class _HeldRuntimeLock:
    async def is_held(self) -> bool:
        return True


def test_execute_manifest_requires_each_of_the_five_allowlisted_types():
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    manifest = _manifest(cutoff=now - timedelta(days=1))

    ordered = WebsiteCommunicationBacklogReconciliation._validate_manifest(
        manifest,
        execute=True,
    )

    assert tuple(item.event_type for item in ordered) == TENANT_WEBSITE_EVENT_TYPES
    assert {
        item.event_type: WebsiteCommunicationBacklogReconciliation._typed_reconciler(
            item
        ).TEMPLATE_KEY
        for item in ordered
    } == TENANT_WEBSITE_EVENT_TEMPLATE_KEYS
    with pytest.raises(
        InstallationEstimateBacklogExecutionBlocked,
        match="website_backlog_manifest_must_cover_allowlist",
    ):
        WebsiteCommunicationBacklogReconciliation._validate_manifest(
            manifest[:-1],
            execute=True,
        )


def test_canonical_cli_requires_explicit_manifest_fields():
    cutoff = "2026-07-31T00:00:00Z"
    argv = ["--operation-id", "11111111-1111-4111-8111-111111111111"]
    for event_type in TENANT_WEBSITE_EVENT_TYPES:
        argv.extend(
            [
                "--event-type",
                event_type,
                "--cutoff",
                cutoff,
                "--expected-count",
                "0",
                "--disposition",
                "terminal_no_send",
            ]
        )
    args = backlog_cli.build_parser().parse_args(argv)

    manifest = backlog_cli._manifest(args)

    assert tuple(item.event_type for item in manifest) == TENANT_WEBSITE_EVENT_TYPES
    assert all(item.expected_count == 0 for item in manifest)
    assert all(item.disposition == "terminal_no_send" for item in manifest)


@pytest.mark.asyncio
async def test_retain_is_reported_as_an_activation_blocker(
    backlog_manifest_session_factory,
):
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    cutoff = now - timedelta(days=1)
    retained_type = TENANT_WEBSITE_EVENT_TYPES[0]
    async with backlog_manifest_session_factory() as session:
        report = await WebsiteCommunicationBacklogReconciliation.reconcile_manifest(
            session,
            manifest=_manifest(cutoff=cutoff, retain={retained_type}),
            operation_id="11111111-1111-4111-8111-111111111111",
            now=now,
        )

    assert report.activation_safe is False
    by_type = {item.event_type: item for item in report.event_types}
    assert by_type[retained_type].activation_blocked is True


@pytest.mark.asyncio
async def test_terminal_no_send_closes_ambiguous_attempt_without_resend(
    backlog_manifest_session_factory,
    monkeypatch,
):
    async def skip_postgres_preflight(cls, session, **kwargs):
        return None

    monkeypatch.setattr(
        InstallationEstimateBacklogReconciliation,
        "_assert_execution_preflight",
        classmethod(skip_postgres_preflight),
    )
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    cutoff = now - timedelta(days=1)
    event_type = TENANT_WEBSITE_EVENT_TYPES[1]
    event = _event(51, event_type, now - timedelta(days=3))
    delivery = CommunicationDelivery(
        delivery_id="5" * 32,
        event_id=event.event_id,
        channel="telegram",
        recipient_key="staff:9",
        destination="1009",
        template_key=TENANT_WEBSITE_EVENT_TEMPLATE_KEYS[event_type],
        template_version=1,
        render_context={"private": "never reported"},
        status="retry",
        priority=20,
        attempts=1,
        max_attempts=8,
        available_at=now,
        last_error_category="provider",
        last_error_code="provider_outcome_unknown",
        created_at=now,
        updated_at=now,
    )
    attempt = CommunicationDeliveryAttempt(
        delivery_id=delivery.delivery_id,
        attempt_no=1,
        started_at=now - timedelta(minutes=2),
        finished_at=now - timedelta(minutes=1),
        provider_started_at=now - timedelta(minutes=2),
        outcome="retry",
        error_category="provider",
        error_code="provider_outcome_unknown",
        ambiguous=True,
    )
    async with backlog_manifest_session_factory() as session:
        session.add_all([event, delivery, attempt])
        await session.commit()
    report = await WebsiteBacklogOperationRunner.execute_manifest(
        backlog_manifest_session_factory,
        manifest=_manifest(
            cutoff=cutoff,
            counts={event_type: 1},
        ),
        operation_id="22222222-2222-4222-8222-222222222222",
        runtime_lock=_HeldRuntimeLock(),
        app_role="primary",
        now=now,
    )

    assert report.activation_safe is True
    type_report = next(
        item for item in report.event_types if item.event_type == event_type
    )
    assert type_report.ambiguous_delivery_count == 1
    assert type_report.terminalized_count == 1
    async with backlog_manifest_session_factory() as session:
        stored_event = await session.get(IntegrationOutboxEvent, event.event_id)
        stored_delivery = await session.get(
            CommunicationDelivery,
            delivery.delivery_id,
        )
        attempts = list(
            (
                await session.execute(
                    select(CommunicationDeliveryAttempt)
                    .where(
                        CommunicationDeliveryAttempt.delivery_id
                        == delivery.delivery_id
                    )
                    .order_by(CommunicationDeliveryAttempt.attempt_no)
                )
            ).scalars()
        )
        operation = await session.get(
            CommunicationWebsiteBacklogOperation,
            "22222222-2222-4222-8222-222222222222",
        )
    assert stored_event is not None and stored_event.status == "dead"
    assert stored_delivery is not None and stored_delivery.status == "canceled"
    assert [item.outcome for item in attempts] == ["retry", "canceled"]
    assert attempts[0].ambiguous is True
    assert operation is not None and operation.state == "succeeded"
    assert operation.outcome_code == "succeeded"
    assert len(operation.aggregate_counts["event_types"]) == 5


@pytest.mark.asyncio
async def test_zero_and_retain_manifest_is_audited_and_replays_idempotently(
    backlog_manifest_session_factory,
    monkeypatch,
):
    async def skip_postgres_preflight(cls, session, **kwargs):
        return None

    monkeypatch.setattr(
        InstallationEstimateBacklogReconciliation,
        "_assert_execution_preflight",
        classmethod(skip_postgres_preflight),
    )
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    operation_id = "33333333-3333-4333-8333-333333333333"
    manifest = _manifest(
        cutoff=now - timedelta(days=1),
        retain={TENANT_WEBSITE_EVENT_TYPES[0]},
    )

    first = await WebsiteBacklogOperationRunner.execute_manifest(
        backlog_manifest_session_factory,
        manifest=manifest,
        operation_id=operation_id,
        runtime_lock=_HeldRuntimeLock(),
        app_role="primary",
        now=now,
    )
    replay = await WebsiteBacklogOperationRunner.execute_manifest(
        backlog_manifest_session_factory,
        manifest=manifest,
        operation_id=operation_id,
        runtime_lock=_HeldRuntimeLock(),
        app_role="primary",
        now=now + timedelta(minutes=1),
    )

    assert first.to_dict() == replay.to_dict()
    assert first.activation_safe is False
    async with backlog_manifest_session_factory() as session:
        operation = await session.get(
            CommunicationWebsiteBacklogOperation,
            operation_id,
        )
        assert operation is not None and operation.state == "succeeded"
        assert len(operation.manifest_summary["event_types"]) == 5
        assert len(operation.aggregate_counts["event_types"]) == 5

    changed = tuple(
        WebsiteBacklogManifestItem(
            event_type=item.event_type,
            cutoff=item.cutoff,
            expected_count=item.expected_count,
            disposition="terminal_no_send",
        )
        for item in manifest
    )
    with pytest.raises(
        WebsiteBacklogOperationManifestMismatch,
        match="website_backlog_operation_manifest_mismatch",
    ):
        await WebsiteBacklogOperationRunner.execute_manifest(
            backlog_manifest_session_factory,
            manifest=changed,
            operation_id=operation_id,
            runtime_lock=_HeldRuntimeLock(),
            app_role="primary",
            now=now,
        )


@pytest.mark.asyncio
async def test_blocked_operation_is_durable_without_event_mutation(
    backlog_manifest_session_factory,
    monkeypatch,
):
    async def skip_postgres_preflight(cls, session, **kwargs):
        return None

    monkeypatch.setattr(
        InstallationEstimateBacklogReconciliation,
        "_assert_execution_preflight",
        classmethod(skip_postgres_preflight),
    )
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    event_type = TENANT_WEBSITE_EVENT_TYPES[0]
    event = _event(71, event_type, now - timedelta(days=3))
    event.status = "pending"
    operation_id = "44444444-4444-4444-8444-444444444444"
    async with backlog_manifest_session_factory() as session:
        session.add(event)
        await session.commit()

    with pytest.raises(
        InstallationEstimateBacklogExecutionBlocked,
        match="website_backlog_expected_count_changed",
    ):
        await WebsiteBacklogOperationRunner.execute_manifest(
            backlog_manifest_session_factory,
            manifest=_manifest(cutoff=now - timedelta(days=1)),
            operation_id=operation_id,
            runtime_lock=_HeldRuntimeLock(),
            app_role="primary",
            now=now,
        )

    async with backlog_manifest_session_factory() as session:
        stored_event = await session.get(IntegrationOutboxEvent, event.event_id)
        operation = await session.get(
            CommunicationWebsiteBacklogOperation,
            operation_id,
        )
        assert stored_event is not None and stored_event.status == "pending"
        assert operation is not None and operation.state == "blocked"
        assert operation.outcome_code == "website_backlog_expected_count_changed"
        assert len(operation.aggregate_counts["event_types"]) == 5


@pytest.mark.asyncio
async def test_started_operation_can_resume_after_a_process_crash(
    backlog_manifest_session_factory,
    monkeypatch,
):
    async def skip_postgres_preflight(cls, session, **kwargs):
        return None

    monkeypatch.setattr(
        InstallationEstimateBacklogReconciliation,
        "_assert_execution_preflight",
        classmethod(skip_postgres_preflight),
    )
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    manifest = _manifest(cutoff=now - timedelta(days=1))
    operation_id = "55555555-5555-4555-8555-555555555555"
    _, summary, fingerprint = WebsiteBacklogOperationRunner.canonical_manifest(
        manifest
    )
    async with backlog_manifest_session_factory() as session:
        session.add(
            CommunicationWebsiteBacklogOperation(
                operation_id=operation_id,
                manifest_fingerprint=fingerprint,
                manifest_summary=summary,
                state="started",
                created_at=now - timedelta(minutes=1),
            )
        )
        await session.commit()

    report = await WebsiteBacklogOperationRunner.execute_manifest(
        backlog_manifest_session_factory,
        manifest=manifest,
        operation_id=operation_id,
        runtime_lock=_HeldRuntimeLock(),
        app_role="primary",
        now=now,
    )

    assert report.activation_safe is True
    async with backlog_manifest_session_factory() as session:
        operation = await session.get(
            CommunicationWebsiteBacklogOperation,
            operation_id,
        )
        assert operation is not None and operation.state == "succeeded"


@pytest.mark.asyncio
async def test_unexpected_failure_is_durable_without_partial_mutation(
    backlog_manifest_session_factory,
    monkeypatch,
):
    async def fail_after_operation_lock(cls, session, **kwargs):
        raise RuntimeError("simulated reconciliation failure")

    monkeypatch.setattr(
        WebsiteCommunicationBacklogReconciliation,
        "reconcile_manifest",
        classmethod(fail_after_operation_lock),
    )
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    operation_id = "66666666-6666-4666-8666-666666666666"

    with pytest.raises(RuntimeError, match="simulated reconciliation failure"):
        await WebsiteBacklogOperationRunner.execute_manifest(
            backlog_manifest_session_factory,
            manifest=_manifest(cutoff=now - timedelta(days=1)),
            operation_id=operation_id,
            runtime_lock=_HeldRuntimeLock(),
            app_role="primary",
            now=now,
        )

    async with backlog_manifest_session_factory() as session:
        operation = await session.get(
            CommunicationWebsiteBacklogOperation,
            operation_id,
        )
        assert operation is not None and operation.state == "failed"
        assert operation.outcome_code == "website_backlog_operation_failed"
        assert len(operation.aggregate_counts["event_types"]) == 5
