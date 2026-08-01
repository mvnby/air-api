from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    CommunicationRuntimeState,
    CommunicationWebsiteCanaryRun,
    IntegrationOutboxEvent,
)
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.contracts import CommunicationRecipientV1
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.runtime_state import (
    CommunicationRuntimeMode,
    CommunicationRuntimeStateService,
)
from services.communications.runtime_config import CommunicationRuntimeConfig
from services.communications.scope_routing import recipients_for_scope
from services.communications.tenant_website_events import (
    TENANT_WEBSITE_CONTACT_LEAD_CREATED_EVENT,
    TENANT_WEBSITE_CONTACT_TEMPLATE_KEY,
)
from services.communications.website_canary_runtime import (
    WebsiteCanaryRuntimeError,
    WebsiteCanaryRuntimeStore,
)
from services.communications.website_canary import (
    TenantWebsiteCommunicationsCanary,
    WebsiteCanaryControlRejected,
    _CanaryEvidence,
)
from services.communications.website_canary_target import (
    WebsiteCanaryScopeMismatch,
    WebsiteCanaryTarget,
)


@pytest.fixture
async def canary_session_factory(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'website-canary.sqlite3'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _target(*, event_id: str = "1" * 32, recipient_key: str = "staff:9"):
    return WebsiteCanaryTarget(
        event_id=event_id,
        event_type=TENANT_WEBSITE_CONTACT_LEAD_CREATED_EVENT,
        tenant_id=7,
        storefront_id=11,
        recipient_key=recipient_key,
    )


def _event(target: WebsiteCanaryTarget, now: datetime) -> IntegrationOutboxEvent:
    return IntegrationOutboxEvent(
        event_id=target.event_id,
        event_type=target.event_type,
        schema_version=1,
        aggregate_type="lead",
        aggregate_id="31",
        aggregate_version=1,
        deduplication_key=f"website-canary-test:{target.event_id}",
        payload={
            "tenant_id": target.tenant_id,
            "storefront_id": target.storefront_id,
            "lead_id": 31,
            "status": "new",
            "name": "Private",
            "phone": "+375290000000",
        },
        status="pending",
        attempts=0,
        available_at=now,
        occurred_at=now,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize(
    "changed",
    [
        {"event_id": "2" * 32},
        {"event_type": "tenant.website.checkout.created"},
        {"tenant_id": 8},
        {"storefront_id": 12},
    ],
)
def test_exact_target_rejects_event_tenant_and_storefront_drift(changed):
    target = _target()
    values = {
        "event_id": target.event_id,
        "event_type": target.event_type,
        "template_key": TENANT_WEBSITE_CONTACT_TEMPLATE_KEY,
        "audience": "tenant_website_management",
        "render_context": {"tenant_id": 7, "storefront_id": 11},
    }
    if "tenant_id" in changed:
        values["render_context"] = {
            **values["render_context"],
            "tenant_id": changed["tenant_id"],
        }
    elif "storefront_id" in changed:
        values["render_context"] = {
            **values["render_context"],
            "storefront_id": changed["storefront_id"],
        }
    else:
        values.update(changed)

    with pytest.raises(WebsiteCanaryScopeMismatch):
        target.assert_event_plan(**values)


def test_exact_recipient_is_selected_from_a_normal_multi_admin_directory():
    target = _target()
    scope = CommunicationProcessingScope.website_canary(
        run_id="11111111-1111-4111-8111-111111111111",
        control_revision=4,
        target=target,
    )
    recipients = [
        CommunicationRecipientV1(
            recipient_key="staff:8",
            destination="1008",
            source="staff",
            staff_user_id=8,
        ),
        CommunicationRecipientV1(
            recipient_key="staff:9",
            destination="1009",
            source="staff",
            staff_user_id=9,
        ),
    ]

    selected = recipients_for_scope(
        scope=scope,
        recipients=recipients,
        event_id=target.event_id,
        template_key=target.template_key,
    )

    assert [recipient.recipient_key for recipient in selected] == ["staff:9"]
    with pytest.raises(
        CommunicationsCanarySafetyError,
        match="website_canary_recipient_scope_changed",
    ):
        recipients_for_scope(
            scope=scope,
            recipients=recipients[:1],
            event_id=target.event_id,
            template_key=target.template_key,
        )


def test_ambiguous_attempt_is_a_terminal_never_resend_outcome():
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    target = _target()
    event = _event(target, now)
    delivery = CommunicationDelivery(
        delivery_id="9" * 32,
        event_id=event.event_id,
        channel="telegram",
        recipient_key=target.recipient_key,
        destination="1009",
        template_key=target.template_key,
        template_version=1,
        render_context=event.payload,
        status="retry",
        attempts=1,
        max_attempts=8,
        available_at=now,
        created_at=now,
        updated_at=now,
    )
    attempt = CommunicationDeliveryAttempt(
        delivery_id=delivery.delivery_id,
        attempt_no=1,
        started_at=now,
        finished_at=now,
        outcome="retry",
        error_category="provider",
        error_code="provider_outcome_unknown",
        ambiguous=True,
    )

    assert TenantWebsiteCommunicationsCanary._classify(
        _CanaryEvidence(event, delivery, attempt, 1)
    ) == ("terminal", "ambiguous")


def test_dead_event_with_nonterminal_delivery_still_refuses_completion():
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    target = _target()
    event = _event(target, now)
    event.status = "dead"
    delivery = CommunicationDelivery(
        delivery_id="8" * 32,
        event_id=event.event_id,
        channel="telegram",
        recipient_key=target.recipient_key,
        destination="1009",
        template_key=target.template_key,
        template_version=1,
        render_context=event.payload,
        status="retry",
        attempts=1,
        max_attempts=8,
        available_at=now,
        created_at=now,
        updated_at=now,
    )

    assert TenantWebsiteCommunicationsCanary._classify(
        _CanaryEvidence(event, delivery, None, 0)
    ) == ("pending", None)


@pytest.mark.asyncio
async def test_runtime_run_is_immutable_idempotent_and_terminally_audited(
    canary_session_factory,
):
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    target = _target()
    run_id = "11111111-1111-4111-8111-111111111111"
    async with canary_session_factory() as session:
        session.add(_event(target, now))
        state = await CommunicationRuntimeStateService.ensure_state(
            session,
            channel="telegram",
        )
        await WebsiteCanaryRuntimeStore.arm_locked(
            session,
            state=state,
            run_id=run_id,
            expected_control_revision=0,
            target=target,
            now=now,
        )
        first_revision = int(state.control_revision)
        replayed = await WebsiteCanaryRuntimeStore.arm_locked(
            session,
            state=state,
            run_id=run_id,
            expected_control_revision=0,
            target=target,
            now=now,
        )
        assert replayed == target
        assert state.control_revision == first_revision

        with pytest.raises(
            WebsiteCanaryRuntimeError,
            match="website_canary_runtime_not_off",
        ):
            await WebsiteCanaryRuntimeStore.arm_locked(
                session,
                state=state,
                run_id="22222222-2222-4222-8222-222222222222",
                expected_control_revision=first_revision,
                target=_target(event_id="2" * 32),
                now=now,
            )

        control = await CommunicationRuntimeStateService.read_control(
            session,
            channel="telegram",
        )
        assert control.website_canary_target == target
        await WebsiteCanaryRuntimeStore.complete_locked(
            session,
            state=state,
            run_id=run_id,
            expected_control_revision=first_revision,
            target=target,
            terminal_outcome="sent",
            now=now,
        )
        await session.commit()

    async with canary_session_factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        run = await session.get(CommunicationWebsiteCanaryRun, run_id)
        assert state is not None and state.mode == CommunicationRuntimeMode.OFF.value
        assert state.website_canary_run_id is None
        assert run is not None and run.state == "terminal"
        assert run.terminal_outcome == "sent"
        assert run.event_id == target.event_id
        assert run.recipient_key == target.recipient_key

        replay = await TenantWebsiteCommunicationsCanary.complete(
            session,
            run_id=run_id,
            target=target,
        )
        assert replay.mode == "completed"
        assert replay.runtime_mode == CommunicationRuntimeMode.OFF.value
        assert replay.terminal_outcome == "sent"


@pytest.mark.asyncio
async def test_stale_revision_is_rejected_and_emergency_off_records_abort(
    canary_session_factory,
):
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    target = _target()
    run_id = "33333333-3333-4333-8333-333333333333"
    async with canary_session_factory() as session:
        session.add(_event(target, now))
        state = await CommunicationRuntimeStateService.ensure_state(
            session,
            channel="telegram",
        )
        with pytest.raises(
            WebsiteCanaryRuntimeError,
            match="website_canary_control_revision_stale",
        ):
            await WebsiteCanaryRuntimeStore.arm_locked(
                session,
                state=state,
                run_id=run_id,
                expected_control_revision=1,
                target=target,
                now=now,
            )
        await WebsiteCanaryRuntimeStore.arm_locked(
            session,
            state=state,
            run_id=run_id,
            expected_control_revision=0,
            target=target,
            now=now,
        )
        await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=CommunicationRuntimeMode.OFF,
        )
        await session.commit()

    async with canary_session_factory() as session:
        run = await session.get(CommunicationWebsiteCanaryRun, run_id)
        assert run is not None
        assert run.state == "terminal"
        assert run.terminal_outcome == "aborted"


@pytest.mark.asyncio
async def test_arm_validates_full_event_and_filters_one_recipient_atomically(
    canary_session_factory,
    monkeypatch,
):
    now = datetime.now(timezone.utc)
    target = _target()
    run_id = "44444444-4444-4444-8444-444444444444"

    async def skip_environment(cls, session, **kwargs):
        return None

    async def recipients(cls, session, **kwargs):
        return [
            CommunicationRecipientV1(
                recipient_key="staff:8",
                destination="1008",
                source="staff",
                staff_user_id=8,
            ),
            CommunicationRecipientV1(
                recipient_key="staff:9",
                destination="1009",
                source="staff",
                staff_user_id=9,
            ),
        ]

    monkeypatch.setattr(
        TenantWebsiteCommunicationsCanary,
        "_preflight_environment",
        classmethod(skip_environment),
    )
    monkeypatch.setattr(
        "services.communications.website_canary."
        "TenantWebsiteManagementRecipientDirectory.list_telegram",
        classmethod(recipients),
    )
    config = CommunicationRuntimeConfig(
        enabled=True,
        allow_all_mode=False,
        app_role="primary",
    )
    async with canary_session_factory() as session:
        event = _event(target, now - timedelta(seconds=2))
        session.add(event)
        state = await CommunicationRuntimeStateService.ensure_state(
            session,
            channel="telegram",
        )
        state.status = "disabled"
        state.instance_id = "canary-worker"
        state.heartbeat_at = now - timedelta(seconds=1)
        await session.commit()

        snapshot = await TenantWebsiteCommunicationsCanary.arm(
            session,
            run_id=run_id,
            target=target,
            expected_control_revision=0,
            config=config,
            bot_token="not-used-by-mocked-preflight",
        )
        await session.commit()

        assert snapshot.mode == "armed"
        assert snapshot.event_id == target.event_id
        assert snapshot.recipient_key == "staff:9"
        control = await CommunicationRuntimeStateService.read_control(
            session,
            channel="telegram",
        )
        assert control.website_canary_target == target

        with pytest.raises(
            WebsiteCanaryControlRejected,
            match="website_canary_recipient_scope_invalid",
        ):
            await TenantWebsiteCommunicationsCanary._assert_exact_recipient(
                session,
                target=_target(recipient_key="staff:10"),
            )
