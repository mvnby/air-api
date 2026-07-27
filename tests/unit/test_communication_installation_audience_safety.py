from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func
from sqlmodel import select

from core.config import settings
from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    ConsumerInbox,
    StaffUser,
)
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.contracts import CommunicationRecipientV1
from services.communications.delivery_materializer import (
    CommunicationDeliveryMaterializer,
)
from services.communications.delivery_worker import CommunicationDeliveryWorker
from services.communications.dispatcher import CommunicationOutboxDispatcher
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.providers.base import ProviderDeliveryResult
from services.communications.recipient_directory import (
    InstallationEstimateOwnerRecipientDirectory,
)
from services.communications.template_registry import (
    CONSUMER_NAME,
    WebsiteTemplateRegistry,
)
from tests.unit.test_communication_delivery_worker import (
    RecordingProvider,
    _seed_delivery,
    worker_session_factory,
)
from tests.unit.test_communications_dispatcher import (
    ALL_SCOPE,
    _event,
    _owner,
    communications_session_factory,
)


@pytest.mark.asyncio
async def test_installation_owner_directory_rejects_duplicate_destination():
    owners = [_owner(303), _owner(303, name="Duplicate")]
    owners[0].id = 1
    owners[1].id = 2

    class StaticResult:
        def scalars(self):
            return self

        def all(self):
            return owners

    class StaticSession:
        async def execute(self, statement):
            return StaticResult()

    with pytest.raises(
        CommunicationsCanarySafetyError,
        match="installation_owner_recipient_duplicate",
    ):
        await InstallationEstimateOwnerRecipientDirectory.list_telegram(
            StaticSession()  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "noncanonical_user",
    [
        StaffUser(
            display_name="Canonical admin",
            status="active",
            roles=["admin"],
            primary_role="admin",
            telegram_id=91001,
        ),
        StaffUser(
            display_name="Legacy admin",
            status="active",
            roles=["admin"],
            primary_role="installer",
            telegram_id=91002,
        ),
        StaffUser(
            display_name="Unknown status owner",
            status="legacy-active",
            roles=["owner"],
            primary_role="owner",
            telegram_id=91003,
        ),
    ],
)
async def test_installation_owner_directory_rejects_normalized_legacy_audience(
    communications_session_factory,
    noncanonical_user,
):
    async with communications_session_factory() as session:
        session.add(noncanonical_user)
        await session.commit()

        with pytest.raises(
            CommunicationsCanarySafetyError,
            match="installation_owner_recipient_count_invalid",
        ):
            await InstallationEstimateOwnerRecipientDirectory.list_telegram(
                session
            )


@pytest.mark.asyncio
async def test_dispatch_all_scope_never_selects_an_event_before_the_watermark(
    communications_session_factory,
):
    watermark = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    scope = CommunicationProcessingScope.all(
        control_revision=1,
        event_created_at_watermark=watermark,
    )
    async with communications_session_factory() as session:
        before = _event(
            22,
            now=watermark - timedelta(seconds=1),
            priority=-100,
        )
        at_watermark = _event(23, now=watermark, priority=100)
        session.add_all([before, at_watermark, _owner(303)])
        await session.commit()

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session,
            scope=scope,
            dispatcher_id="dispatcher-a",
            now=watermark,
        )
        await session.commit()

        assert outcome is not None
        assert outcome.event_id == at_watermark.event_id
        assert outcome.outcome == "materialized"
        await session.refresh(before)
        assert before.status == "pending"
        assert before.attempts == 0


@pytest.mark.asyncio
async def test_installation_audience_excludes_managers_and_admin_fallback(
    communications_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "700,701", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 702, raising=False)
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    async with communications_session_factory() as session:
        session.add_all(
            [
                _event(24, now=now),
                _owner(303),
                StaffUser(
                    display_name="Manager",
                    status="active",
                    roles=["manager"],
                    primary_role="manager",
                    telegram_id=404,
                ),
            ]
        )
        await session.commit()

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session,
            scope=ALL_SCOPE,
            dispatcher_id="dispatcher-a",
            now=now,
        )
        await session.commit()

        assert outcome is not None
        assert outcome.outcome == "materialized"
        destinations = list(
            (
                await session.execute(
                    select(CommunicationDelivery.destination)
                )
            ).scalars()
        )
        assert destinations == ["303"]


@pytest.mark.asyncio
async def test_dispatch_fails_closed_when_any_active_owner_is_invalid(
    communications_session_factory,
):
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    async with communications_session_factory() as session:
        event = _event(25, now=now, max_attempts=2)
        session.add_all(
            [
                event,
                _owner(303),
                StaffUser(
                    display_name="Owner without Telegram",
                    status="active",
                    roles=["owner"],
                    primary_role="owner",
                    telegram_id=None,
                ),
            ]
        )
        await session.commit()

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session,
            scope=ALL_SCOPE,
            dispatcher_id="dispatcher-a",
            now=now,
        )
        await session.commit()

        assert outcome is not None
        assert outcome.outcome == "retry_scheduled"
        assert event.last_error_code == "installation_owner_recipient_invalid"
        assert (
            await session.execute(
                select(func.count(CommunicationDelivery.delivery_id))
            )
        ).scalar_one() == 0


@pytest.mark.asyncio
async def test_dispatch_rejects_existing_inbox_after_exact_owner_set_drift(
    communications_session_factory,
):
    now = datetime(2026, 7, 12, 3, 0, tzinfo=timezone.utc)
    async with communications_session_factory() as session:
        event = _event(62, now=now)
        first_owner = _owner(700)
        session.add_all([event, first_owner])
        await session.flush()
        plan = WebsiteTemplateRegistry.plan(event)
        await CommunicationDeliveryMaterializer.materialize(
            session,
            event=event,
            plan=plan,
            recipients=[
                CommunicationRecipientV1(
                    recipient_key=f"staff:{first_owner.id}",
                    destination="700",
                    source="staff",
                    staff_user_id=first_owner.id,
                )
            ],
            now=now,
        )
        session.add(
            ConsumerInbox(
                consumer_name=CONSUMER_NAME,
                event_id=event.event_id,
                handler_version=1,
                received_at=now,
                processed_at=now,
            )
        )
        session.add(_owner(701, name="New owner"))
        await session.commit()

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session,
            scope=ALL_SCOPE,
            dispatcher_id="dispatcher-a",
            now=now,
        )
        await session.commit()

        assert outcome is not None
        assert outcome.outcome == "dead"
        assert event.status == "dead"
        assert event.last_error_code == "ConsumerInboxConsistencyError"


@pytest.mark.asyncio
async def test_worker_revalidates_recipient_and_cancels_without_network(
    worker_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    owner_id, delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=2,
        telegram_id=202002,
    )
    async with worker_session_factory() as session:
        owner = await session.get(StaffUser, owner_id)
        assert owner is not None
        owner.status = "blocked"
        session.add(owner)
        await session.commit()

    provider = RecordingProvider(
        worker_session_factory,
        {"202002": ProviderDeliveryResult.sent("must-not-send")},
    )
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="test-worker",
        lease_seconds=60,
    )

    outcome = await worker.run_once()

    assert outcome.outcome == "canceled"
    assert provider.calls == []
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        assert row.status == "canceled"
        assert row.last_error_code == "recipient_inactive"
        assert row.finished_at is not None
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 1),
        )
        assert attempt is not None
        assert attempt.outcome == "canceled"
        assert attempt.provider_latency_ms is None


@pytest.mark.asyncio
async def test_worker_cancels_when_materialized_set_no_longer_matches_all_owners(
    worker_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "999999", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 999998, raising=False)
    _, delivery_id = await _seed_delivery(
        worker_session_factory,
        sequence=22,
        telegram_id=220022,
    )
    async with worker_session_factory() as session:
        session.add(
            StaffUser(
                display_name="Owner added after materialization",
                status="active",
                roles=["owner"],
                primary_role="owner",
                telegram_id=220023,
            )
        )
        await session.commit()

    provider = RecordingProvider(
        worker_session_factory,
        {"220022": ProviderDeliveryResult.sent("must-not-send")},
    )
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="exact-owner-set-worker",
        lease_seconds=60,
    )

    outcome = await worker.run_once()

    assert outcome.outcome == "canceled"
    assert provider.calls == []
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        assert row.status == "canceled"
        assert row.last_error_code == "recipient_inactive"
