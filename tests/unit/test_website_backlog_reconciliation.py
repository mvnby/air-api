from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
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
        report = await WebsiteCommunicationBacklogReconciliation.reconcile_manifest(
            session,
            manifest=_manifest(
                cutoff=cutoff,
                counts={event_type: 1},
            ),
            operation_id="22222222-2222-4222-8222-222222222222",
            execute=True,
            now=now,
        )
        await session.commit()

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
    assert stored_event is not None and stored_event.status == "dead"
    assert stored_delivery is not None and stored_delivery.status == "canceled"
    assert [item.outcome for item in attempts] == ["retry", "canceled"]
    assert attempts[0].ambiguous is True
