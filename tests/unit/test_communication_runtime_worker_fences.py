from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from core.config import settings
from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    IntegrationOutboxEvent,
    StaffUser,
)
from services.communications.contracts import InstallationEstimateLeadCreatedPayloadV1
from services.communications.delivery_service import CommunicationDeliveryService
from services.communications.delivery_worker import CommunicationDeliveryWorker
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.providers.base import ProviderDeliveryResult
from services.communications.runtime_state import (
    CommunicationRuntimeMode,
    CommunicationRuntimeModeBlocked,
    CommunicationRuntimeStateService,
)
from services.communications.template_registry import (
    CONTACT_LEAD_TEMPLATE_KEY,
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    INSTALLATION_ESTIMATE_TEMPLATE_KEY,
    ORDER_TEMPLATE_KEY,
    PUBLIC_CONTACT_LEAD_CREATED_EVENT,
    PUBLIC_ORDER_CREATED_EVENT,
)
from tests.unit.tenant_website_test_support import (
    add_tenant_members,
    ensure_tenant_website_scope,
)

ALL_SCOPE = CommunicationProcessingScope.all(
    control_revision=0,
    event_created_at_watermark=datetime(2000, 1, 1, tzinfo=timezone.utc),
)
RUN_ID_A = "123e4567-e89b-42d3-a456-426614174000"


@pytest.fixture
async def worker_session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fences.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def seed_delivery(
    session_factory,
    *,
    sequence: int,
    telegram_id: int,
    template_key: str = INSTALLATION_ESTIMATE_TEMPLATE_KEY,
    render_context: dict | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        await ensure_tenant_website_scope(session)
        recipient_role = (
            "owner"
            if template_key == INSTALLATION_ESTIMATE_TEMPLATE_KEY
            else "manager"
        )
        owner = StaffUser(
            display_name=f"Owner {sequence}",
            status="active",
            roles=[recipient_role],
            primary_role=recipient_role,
            telegram_id=telegram_id,
        )
        if template_key == INSTALLATION_ESTIMATE_TEMPLATE_KEY:
            await add_tenant_members(session, owner)
        else:
            session.add(owner)
            await session.flush()
        assert owner.id is not None
        delivery_id = f"{sequence:032x}"
        event_id = f"{sequence + 1000:032x}"
        event_type = {
            CONTACT_LEAD_TEMPLATE_KEY: PUBLIC_CONTACT_LEAD_CREATED_EVENT,
            ORDER_TEMPLATE_KEY: PUBLIC_ORDER_CREATED_EVENT,
        }.get(template_key, INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT)
        session.add(
            IntegrationOutboxEvent(
                event_id=event_id,
                event_type=event_type,
                schema_version=1,
                aggregate_type="order",
                aggregate_id=str(sequence),
                deduplication_key=f"runtime-fence:{sequence}",
                payload={},
                status="published",
                available_at=now,
                occurred_at=now,
                published_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            CommunicationDelivery(
                delivery_id=delivery_id,
                event_id=event_id,
                channel="telegram",
                recipient_key=f"staff:{owner.id}",
                destination=str(telegram_id),
                template_key=template_key,
                template_version=1,
                render_context=render_context
                or InstallationEstimateLeadCreatedPayloadV1(
                    tenant_id=1,
                    storefront_id=1,
                    order_id=sequence,
                    status="new_lead",
                    name=f"Lead {sequence}",
                    phone="+375291112233",
                    description="Нужна предварительная оценка монтажа",
                    attachment_count=1,
                    photo_categories=("Место внутреннего блока",),
                ).model_dump(mode="json"),
                status="queued",
                priority=100,
                attempts=0,
                max_attempts=3,
                available_at=now - timedelta(seconds=1),
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
        return delivery_id


@pytest.mark.asyncio
async def test_runtime_scope_leaves_contact_and_order_deliveries_untouched(
    worker_session_factory,
    monkeypatch,
):
    """The production rollout must not consume legacy website delivery types."""

    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    installation_delivery_id = await seed_delivery(
        worker_session_factory,
        sequence=11,
        telegram_id=111011,
    )
    contact_delivery_id = await seed_delivery(
        worker_session_factory,
        sequence=12,
        telegram_id=111012,
        template_key=CONTACT_LEAD_TEMPLATE_KEY,
        render_context={"legacy": "contact"},
    )
    order_delivery_id = await seed_delivery(
        worker_session_factory,
        sequence=13,
        telegram_id=111013,
        template_key=ORDER_TEMPLATE_KEY,
        render_context={"legacy": "order"},
    )
    provider = ImmediateProvider()
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="allowlist-fence-worker",
        lease_seconds=60,
    )

    assert (await worker.run_once()).outcome == "sent"
    assert (await worker.run_once()).outcome == "idle"
    assert provider.calls == 1

    async with worker_session_factory() as session:
        installation = await session.get(
            CommunicationDelivery, installation_delivery_id
        )
        contact = await session.get(CommunicationDelivery, contact_delivery_id)
        order = await session.get(CommunicationDelivery, order_delivery_id)
        assert installation is not None and installation.status == "sent"
        assert contact is not None and contact.status == "queued"
        assert contact.attempts == 0
        assert order is not None and order.status == "queued"
        assert order.attempts == 0


async def own_runtime_mode(session_factory) -> CommunicationProcessingScope:
    async with session_factory() as session:
        state = await CommunicationRuntimeStateService.ensure_state(
            session,
            channel="telegram",
        )
        state.mode = CommunicationRuntimeMode.ALL.value
        state.canary_run_id = None
        state.control_revision = int(state.control_revision) + 1
        state.installation_estimate_watermark_at = (
            state.installation_estimate_watermark_at
            or datetime(2000, 1, 1, tzinfo=timezone.utc)
        )
        session.add(state)
        await session.flush()
        control = CommunicationRuntimeStateService._to_control(state)
        await CommunicationRuntimeStateService.take_ownership(
            session,
            channel="telegram",
            instance_id="mode-fence-worker",
        )
        await session.commit()
        return CommunicationProcessingScope.all(
            control_revision=control.control_revision,
            event_created_at_watermark=(
                control.installation_estimate_watermark_at
            ),
        )


async def set_runtime_mode(
    session_factory,
    mode: CommunicationRuntimeMode,
) -> None:
    async with session_factory() as session:
        current = await CommunicationRuntimeStateService.read_control(
            session,
            channel="telegram",
        )
        if (
            current.mode != CommunicationRuntimeMode.OFF
            and mode != CommunicationRuntimeMode.OFF
        ):
            await CommunicationRuntimeStateService.set_mode(
                session,
                channel="telegram",
                mode=CommunicationRuntimeMode.OFF,
            )
        await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=mode,
            canary_run_id=(
                RUN_ID_A if mode == CommunicationRuntimeMode.CANARY else None
            ),
        )
        await session.commit()


def active_mode_safety_check(session_factory, scope):
    async def safety_check() -> None:
        async with session_factory() as session:
            await CommunicationRuntimeStateService.assert_owned_processing_scope(
                session,
                channel="telegram",
                instance_id="mode-fence-worker",
                scope=scope,
            )

    return safety_check


class ImmediateProvider:
    channel = "telegram"

    def __init__(self):
        self.calls = 0

    async def send(self, **_kwargs):
        self.calls += 1
        return ProviderDeliveryResult.sent("immediate-message")

    async def close(self):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("blocked_call", "expected_status", "expected_attempts"),
    [(2, "queued", 0), (3, "retry", 1)],
)
async def test_runtime_safety_check_fences_claim_and_provider_send(
    worker_session_factory,
    monkeypatch,
    blocked_call,
    expected_status,
    expected_attempts,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    delivery_id = await seed_delivery(
        worker_session_factory,
        sequence=14 + blocked_call,
        telegram_id=141000 + blocked_call,
    )
    provider = ImmediateProvider()
    safety_calls = 0

    async def safety_check():
        nonlocal safety_calls
        safety_calls += 1
        if safety_calls == blocked_call:
            raise RuntimeError("runtime ownership fence lost")

    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="generic-fence-worker",
        lease_seconds=60,
        safety_check=safety_check,
    )

    with pytest.raises(RuntimeError, match="ownership fence lost"):
        await worker.run_once()
    assert provider.calls == 0
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        assert row.status == expected_status
        assert row.attempts == expected_attempts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "blocked_mode",
    [CommunicationRuntimeMode.OFF, CommunicationRuntimeMode.CANARY],
)
async def test_db_mode_flip_before_claim_leaves_delivery_queued(
    worker_session_factory,
    monkeypatch,
    blocked_mode,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    delivery_id = await seed_delivery(
        worker_session_factory,
        sequence=16,
        telegram_id=161016,
    )
    scope = await own_runtime_mode(worker_session_factory)
    provider = ImmediateProvider()
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=scope,
        provider=provider,
        worker_id="mode-fence-worker",
        lease_seconds=60,
        safety_check=active_mode_safety_check(worker_session_factory, scope),
    )
    original_recovery = worker._recover_expired_leases

    async def recover_then_flip_mode():
        recovery = await original_recovery()
        await set_runtime_mode(worker_session_factory, blocked_mode)
        return recovery

    monkeypatch.setattr(worker, "_recover_expired_leases", recover_then_flip_mode)

    with pytest.raises(CommunicationRuntimeModeBlocked) as blocked:
        await worker.run_once()
    assert blocked.value.mode == blocked_mode
    assert provider.calls == 0
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        assert row.status == "queued"
        assert row.attempts == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "blocked_mode",
    [CommunicationRuntimeMode.OFF, CommunicationRuntimeMode.CANARY],
)
async def test_db_mode_flip_before_provider_send_releases_pre_provider_claim(
    worker_session_factory,
    monkeypatch,
    blocked_mode,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    delivery_id = await seed_delivery(
        worker_session_factory,
        sequence=17,
        telegram_id=171017,
    )
    scope = await own_runtime_mode(worker_session_factory)
    provider = ImmediateProvider()
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=scope,
        provider=provider,
        worker_id="mode-fence-worker",
        lease_seconds=60,
        safety_check=active_mode_safety_check(worker_session_factory, scope),
    )
    original_recipient_check = worker._recipient_is_current

    async def check_then_flip_mode(claim, plan):
        is_current = await original_recipient_check(claim, plan)
        await set_runtime_mode(worker_session_factory, blocked_mode)
        return is_current

    monkeypatch.setattr(
        worker,
        "_recipient_is_current",
        check_then_flip_mode,
    )

    with pytest.raises(CommunicationRuntimeModeBlocked) as blocked:
        await worker.run_once()
    assert blocked.value.mode == blocked_mode
    assert provider.calls == 0
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        attempt = await session.get(
            CommunicationDeliveryAttempt,
            (delivery_id, 1),
        )
        assert row is not None
        assert row.status == "retry"
        assert row.attempts == 1
        assert row.worker_id is None
        assert row.lease_token is None
        assert row.lease_expires_at is None
        assert attempt is not None
        assert attempt.outcome == "retry"
        assert attempt.provider_started_at is None
        assert attempt.ambiguous is False
        assert attempt.error_code == "runtime_control_fenced_before_provider"


@pytest.mark.asyncio
async def test_runtime_db_timeout_fails_closed_before_claim(
    worker_session_factory,
    monkeypatch,
):
    delivery_id = await seed_delivery(
        worker_session_factory,
        sequence=18,
        telegram_id=181018,
    )
    provider = ImmediateProvider()

    async def blocked_recovery(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(
        CommunicationDeliveryService,
        "recover_expired_leases",
        blocked_recovery,
    )
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="db-timeout-worker",
        lease_seconds=60,
        db_operation_timeout_seconds=0.01,
    )

    with pytest.raises(TimeoutError):
        await worker.run_once()
    assert provider.calls == 0
    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        assert row is not None
        assert row.status == "queued"
        assert row.attempts == 0


@pytest.mark.asyncio
async def test_terminal_db_timeout_is_recovered_as_ambiguous_attempt(
    worker_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ADMIN_IDS", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_ID", 0, raising=False)
    delivery_id = await seed_delivery(
        worker_session_factory,
        sequence=19,
        telegram_id=191019,
    )
    provider = ImmediateProvider()
    mark_sent_entered = asyncio.Event()

    async def blocked_mark_sent(*_args, **_kwargs):
        mark_sent_entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(
        CommunicationDeliveryService,
        "mark_sent",
        blocked_mark_sent,
    )
    worker = CommunicationDeliveryWorker(
        session_factory=worker_session_factory,
        scope=ALL_SCOPE,
        provider=provider,
        worker_id="terminal-timeout-worker",
        lease_seconds=60,
    )
    original_mark_sent = worker._mark_sent

    def mark_sent_with_bounded_timeout(*args, **kwargs):
        # Select the terminal DB operation explicitly instead of racing every
        # earlier SQLite operation against one wall-clock timeout. Production
        # still uses the same bounded operation and fail-closed cancellation.
        worker._db_operation_timeout_seconds = 0.01
        return original_mark_sent(*args, **kwargs)

    monkeypatch.setattr(worker, "_mark_sent", mark_sent_with_bounded_timeout)

    with pytest.raises(TimeoutError):
        await worker.run_once()
    assert mark_sent_entered.is_set()
    assert provider.calls == 1
    async with worker_session_factory() as session:
        running = await session.get(CommunicationDelivery, delivery_id)
        assert running is not None
        assert running.status == "running"
        assert running.lease_expires_at is not None
        lease_expires_at = running.lease_expires_at
        if lease_expires_at.tzinfo is None:
            lease_expires_at = lease_expires_at.replace(tzinfo=timezone.utc)
        recovery_time = lease_expires_at + timedelta(seconds=1)
        attempt = await session.get(CommunicationDeliveryAttempt, (delivery_id, 1))
        assert attempt is not None
        assert attempt.outcome == "running"
        recovered = await CommunicationDeliveryService.recover_expired_leases(
            session,
            scope=ALL_SCOPE,
            now=recovery_time,
        )
        await session.commit()
        assert recovered.retry_count == 0
        assert recovered.dead_count == 1

    async with worker_session_factory() as session:
        row = await session.get(CommunicationDelivery, delivery_id)
        attempt = await session.get(CommunicationDeliveryAttempt, (delivery_id, 1))
        assert row is not None
        assert row.status == "dead"
        assert attempt is not None
        assert attempt.outcome == "dead"
        assert attempt.ambiguous is True
        assert attempt.error_code == "lease_expired_after_provider"
