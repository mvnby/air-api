from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from core.config import settings
from models import CommunicationDelivery, IntegrationOutboxEvent, StaffUser
from services.communications.canary import CommunicationsTelegramCanary
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.contracts import TelegramCanaryRequestedPayloadV1
from services.communications.dispatcher import CommunicationOutboxDispatcher
from services.communications.delivery_worker import CommunicationDeliveryWorker
from services.communications.recipient_directory import (
    OperationsCanaryRecipientDirectory,
)
from services.communications.template_registry import (
    TELEGRAM_CANARY_REQUESTED_EVENT,
    TELEGRAM_CANARY_TEMPLATE_KEY,
    InvalidCommunicationEventPayload,
    WebsiteTemplateRegistry,
    telegram_canary_deduplication_key,
    telegram_canary_idempotency_key,
)
from services.communications.templates.operations import (
    TELEGRAM_CANARY_MESSAGE_V1,
    render_telegram_canary_v1,
)


RUN_ID_A = "123e4567-e89b-42d3-a456-426614174000"


@pytest.fixture
async def canary_session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'canary.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _staff(
    name: str,
    telegram_id: int | None,
    *,
    role: str = "owner",
    status: str = "active",
) -> StaffUser:
    return StaffUser(
        display_name=name,
        status=status,
        roles=[role],
        primary_role=role,
        telegram_id=telegram_id,
    )


def _canary_event(
    payload: dict,
    *,
    run_id: str = RUN_ID_A,
) -> IntegrationOutboxEvent:
    now = datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)
    return IntegrationOutboxEvent(
        event_id=CommunicationsTelegramCanary.event_id(run_id),
        event_type=TELEGRAM_CANARY_REQUESTED_EVENT,
        schema_version=1,
        aggregate_type="communications_canary",
        aggregate_id=run_id,
        aggregate_version=1,
        deduplication_key=telegram_canary_deduplication_key(run_id),
        idempotency_key=telegram_canary_idempotency_key(run_id),
        payload=payload,
        priority=0,
        max_attempts=1,
        available_at=now,
        occurred_at=now,
        created_at=now,
        updated_at=now,
    )


def test_canary_contract_accepts_only_two_stable_safe_staff_keys():
    payload = TelegramCanaryRequestedPayloadV1(
        run_id=RUN_ID_A,
        recipient_keys=("staff:2", "staff:10")
    )
    assert payload.model_dump(mode="json") == {
        "run_id": RUN_ID_A,
        "recipient_keys": ["staff:2", "staff:10"]
    }

    invalid_payloads = [
        {"run_id": RUN_ID_A, "recipient_keys": ["staff:1", "staff:1"]},
        {"run_id": RUN_ID_A, "recipient_keys": ["staff:10", "staff:2"]},
        {
            "run_id": RUN_ID_A,
            "recipient_keys": ["legacy-telegram:1", "staff:2"],
        },
        {
            "run_id": RUN_ID_A,
            "recipient_keys": ["staff:1", "staff:2"],
            "text": "custom",
        },
        {"run_id": "release-candidate", "recipient_keys": ["staff:1", "staff:2"]},
        {
            "run_id": "123e4567-e89b-12d3-a456-426614174000",
            "recipient_keys": ["staff:1", "staff:2"],
        },
        {
            "run_id": "123e4567-e89b-42d3-7456-426614174000",
            "recipient_keys": ["staff:1", "staff:2"],
        },
        {
            "run_id": RUN_ID_A.upper(),
            "recipient_keys": ["staff:1", "staff:2"],
        },
    ]
    for invalid in invalid_payloads:
        with pytest.raises(ValidationError):
            TelegramCanaryRequestedPayloadV1.model_validate(invalid)


def test_canary_registry_renders_only_fixed_text_and_rejects_html_injection():
    payload = TelegramCanaryRequestedPayloadV1(
        run_id=RUN_ID_A,
        recipient_keys=("staff:1", "staff:2")
    ).model_dump(mode="json")
    plan = WebsiteTemplateRegistry.plan(_canary_event(payload))

    assert plan.audience == "operations_canary"
    assert plan.template_key == TELEGRAM_CANARY_TEMPLATE_KEY
    rendered = WebsiteTemplateRegistry.render(plan)
    assert rendered == TELEGRAM_CANARY_MESSAGE_V1.format(
        short_run_id=RUN_ID_A[:8]
    )
    assert RUN_ID_A[:8] in rendered
    assert RUN_ID_A not in rendered
    assert "staff:1" not in rendered
    assert "staff:2" not in rendered
    assert len(rendered) <= 4096

    injected = {**payload, "message": "<script>secret()</script>"}
    with pytest.raises(ValidationError):
        render_telegram_canary_v1(injected)
    with pytest.raises(InvalidCommunicationEventPayload):
        WebsiteTemplateRegistry.plan(_canary_event(injected))

    retryable_copy = _canary_event(payload)
    retryable_copy.max_attempts = 8
    with pytest.raises(InvalidCommunicationEventPayload):
        WebsiteTemplateRegistry.plan(retryable_copy)


@pytest.mark.asyncio
async def test_canary_directory_uses_exact_active_owners_without_manager_or_legacy(
    canary_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "999999", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 888888, raising=False)
    async with canary_session_factory() as session:
        session.add_all(
            [
                _staff("Owner One", 101),
                _staff("Manager", 202, role="manager"),
                _staff("Owner Two", 303),
                _staff("Inactive Owner", 404, status="inactive"),
            ]
        )
        await session.flush()

        recipients = await OperationsCanaryRecipientDirectory.list_telegram(session)

        assert [recipient.recipient_key for recipient in recipients] == [
            "staff:1",
            "staff:3",
        ]
        assert [recipient.destination for recipient in recipients] == ["101", "303"]
        assert all(recipient.source == "staff" for recipient in recipients)
        assert all(not key.startswith("legacy-") for key in [r.recipient_key for r in recipients])

        with pytest.raises(CommunicationsCanarySafetyError) as changed:
            await OperationsCanaryRecipientDirectory.list_telegram(
                session,
                required_recipient_keys=("staff:1", "staff:2"),
            )
        assert changed.value.error_code == "active_owner_recipient_snapshot_changed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("owners", "error_code"),
    [
        ([101], "active_owner_recipient_count_invalid"),
        ([101, 202, 303], "active_owner_recipient_count_invalid"),
        ([101, None], "active_owner_recipient_invalid"),
        ([101, -202], "active_owner_recipient_invalid"),
    ],
)
async def test_canary_directory_fails_closed_for_invalid_owner_set(
    canary_session_factory,
    owners,
    error_code,
):
    async with canary_session_factory() as session:
        session.add_all(
            [_staff(f"Owner {index}", value) for index, value in enumerate(owners)]
        )
        await session.flush()

        with pytest.raises(CommunicationsCanarySafetyError) as exc_info:
            await OperationsCanaryRecipientDirectory.list_telegram(session)
        assert exc_info.value.error_code == error_code


@pytest.mark.asyncio
async def test_canary_dispatcher_materializes_only_snapshotted_owners(
    canary_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "999999", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 888888, raising=False)
    now = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)
    async with canary_session_factory() as session:
        session.add_all(
            [
                _staff("Owner One", 101),
                _staff("Owner Two", 202),
                _staff("Manager", 303, role="manager"),
            ]
        )
        await session.flush()
        recipients = await OperationsCanaryRecipientDirectory.list_telegram(session)
        result = await CommunicationsTelegramCanary.enqueue(
            session,
            run_id=RUN_ID_A,
            recipient_keys=tuple(item.recipient_key for item in recipients),
            occurred_at=now,
        )
        await session.commit()

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session,
            dispatcher_id="canary-test-dispatcher",
            now=now,
        )
        await session.commit()

        assert outcome is not None
        assert outcome.outcome == "materialized"
        assert outcome.delivery_count == 2
        deliveries = list(
            (
                await session.execute(
                    select(CommunicationDelivery).order_by(
                        CommunicationDelivery.recipient_key.asc()
                    )
                )
            ).scalars()
        )
        assert [delivery.recipient_key for delivery in deliveries] == [
            "staff:1",
            "staff:2",
        ]
        assert [delivery.destination for delivery in deliveries] == ["101", "202"]
        assert all(delivery.max_attempts == 1 for delivery in deliveries)
        assert result.event.status == "published"


@pytest.mark.asyncio
async def test_canary_dispatcher_dies_closed_when_owner_snapshot_changes(
    canary_session_factory,
):
    now = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)
    async with canary_session_factory() as session:
        owner_one = _staff("Owner One", 101)
        owner_two = _staff("Owner Two", 202)
        replacement = _staff("Manager", 303, role="manager")
        session.add_all([owner_one, owner_two, replacement])
        await session.flush()
        await CommunicationsTelegramCanary.enqueue(
            session,
            run_id=RUN_ID_A,
            recipient_keys=(f"staff:{owner_one.id}", f"staff:{owner_two.id}"),
            occurred_at=now,
        )
        await session.commit()

        owner_one.primary_role = "manager"
        owner_one.roles = ["manager"]
        replacement.primary_role = "owner"
        replacement.roles = ["owner"]
        session.add_all([owner_one, replacement])
        await session.commit()

        outcome = await CommunicationOutboxDispatcher.dispatch_next(
            session,
            dispatcher_id="canary-test-dispatcher",
            now=now,
        )
        await session.commit()

        assert outcome is not None
        assert outcome.outcome == "dead"
        assert outcome.delivery_count == 0
        stored_event = await session.get(
            IntegrationOutboxEvent,
            CommunicationsTelegramCanary.event_id(RUN_ID_A),
        )
        assert stored_event is not None
        assert (
            stored_event.last_error_code
            == "active_owner_recipient_snapshot_changed"
        )
        assert (
            await session.execute(select(func.count(CommunicationDelivery.delivery_id)))
        ).scalar_one() == 0


class _NeverSendProvider:
    channel = "telegram"

    def __init__(self) -> None:
        self.calls = 0

    async def send(self, *, destination: str, text: str, delivery_id: str):
        self.calls += 1
        raise AssertionError("Canary provider must not be called after snapshot drift")

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_canary_worker_cancels_without_provider_call_after_owner_snapshot_drift(
    canary_session_factory,
):
    now = datetime.now(timezone.utc)
    async with canary_session_factory() as session:
        owner_one = _staff("Owner One", 101)
        owner_two = _staff("Owner Two", 202)
        replacement = _staff("Manager", 303, role="manager")
        session.add_all([owner_one, owner_two, replacement])
        await session.flush()
        session.add(
            CommunicationDelivery(
                delivery_id="c" * 32,
                event_id=CommunicationsTelegramCanary.event_id(RUN_ID_A),
                channel="telegram",
                recipient_key=f"staff:{owner_two.id}",
                destination="202",
                template_key=TELEGRAM_CANARY_TEMPLATE_KEY,
                template_version=1,
                render_context={
                    "run_id": RUN_ID_A,
                    "recipient_keys": [
                        f"staff:{owner_one.id}",
                        f"staff:{owner_two.id}",
                    ]
                },
                status="queued",
                attempts=0,
                max_attempts=1,
                available_at=now - timedelta(seconds=1),
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

        owner_one.primary_role = "manager"
        owner_one.roles = ["manager"]
        replacement.primary_role = "owner"
        replacement.roles = ["owner"]
        session.add_all([owner_one, replacement])
        await session.commit()

    provider = _NeverSendProvider()
    worker = CommunicationDeliveryWorker(
        session_factory=canary_session_factory,
        provider=provider,
        worker_id="canary-worker-test",
        lease_seconds=60,
    )
    outcome = await worker.run_once()

    assert outcome.outcome == "canceled"
    assert provider.calls == 0
    async with canary_session_factory() as session:
        delivery = await session.get(CommunicationDelivery, "c" * 32)
        assert delivery is not None
        assert delivery.status == "canceled"
        assert delivery.attempts == 1


@pytest.mark.asyncio
async def test_canary_worker_cancels_injected_render_context_without_provider_call(
    canary_session_factory,
):
    now = datetime.now(timezone.utc)
    async with canary_session_factory() as session:
        session.add_all([_staff("Owner One", 101), _staff("Owner Two", 202)])
        await session.flush()
        session.add(
            CommunicationDelivery(
                delivery_id="d" * 32,
                event_id=CommunicationsTelegramCanary.event_id(RUN_ID_A),
                channel="telegram",
                recipient_key="staff:1",
                destination="101",
                template_key=TELEGRAM_CANARY_TEMPLATE_KEY,
                template_version=1,
                render_context={
                    "run_id": RUN_ID_A,
                    "recipient_keys": ["staff:1", "staff:2"],
                    "message": "<script>must not render</script>",
                },
                status="queued",
                attempts=0,
                max_attempts=1,
                available_at=now - timedelta(seconds=1),
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    provider = _NeverSendProvider()
    worker = CommunicationDeliveryWorker(
        session_factory=canary_session_factory,
        provider=provider,
        worker_id="canary-worker-test",
        lease_seconds=60,
    )
    outcome = await worker.run_once()

    assert outcome.outcome == "canceled"
    assert provider.calls == 0
