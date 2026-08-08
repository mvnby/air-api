from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    CommunicationRuntimeState,
    IntegrationOutboxEvent,
    StaffUser,
    TenantMembership,
)
import scripts.communications_installation_notifications as command_module
from scripts.communications_installation_notifications import (
    build_parser,
    run_command,
)
from services.communications.installation_notifications import (
    InstallationNotificationControlRejected,
    InstallationNotificationOperations,
)
from services.communications.runtime_config import CommunicationRuntimeConfig
from services.communications.template_registry import (
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    INSTALLATION_ESTIMATE_TEMPLATE_KEY,
)
from tests.unit.tenant_website_test_support import (
    TENANT_WEBSITE_SCOPE_TABLES,
    add_tenant_members,
    ensure_tenant_website_scope,
)


def _runtime_config(**overrides) -> CommunicationRuntimeConfig:
    config = CommunicationRuntimeConfig(
        enabled=True,
        app_role="primary",
        allow_all_mode=True,
        instance_id="installation-operator-test",
        poll_seconds=0.01,
        heartbeat_seconds=10,
        lock_retry_seconds=0.01,
        lock_check_seconds=0.01,
        db_probe_timeout_seconds=0.1,
        fencing_seconds=3,
        shutdown_seconds=0.2,
        provider_timeout_seconds=1,
        provider_close_seconds=0.1,
        lease_seconds=30,
    )
    return replace(config, **overrides)


@pytest.fixture
async def operator_session_factory(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'installation-operator.sqlite3'}"
    )
    async with engine.begin() as connection:
        for table in TENANT_WEBSITE_SCOPE_TABLES:
            await connection.run_sync(table.create)
        await connection.run_sync(StaffUser.__table__.create)
        await connection.run_sync(TenantMembership.__table__.create)
        await connection.run_sync(IntegrationOutboxEvent.__table__.create)
        await connection.run_sync(CommunicationDelivery.__table__.create)
        await connection.run_sync(CommunicationDeliveryAttempt.__table__.create)
        await connection.run_sync(CommunicationRuntimeState.__table__.create)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def allow_sqlite_operator_checks(monkeypatch):
    async def writable_primary(cls, session):
        return None

    async def sole_lock_owner(cls, session, *, lock_name):
        return 1

    monkeypatch.setattr(
        InstallationNotificationOperations,
        "_database_primary_blocker",
        classmethod(writable_primary),
    )
    monkeypatch.setattr(
        InstallationNotificationOperations,
        "_runtime_lock_owner_count",
        classmethod(sole_lock_owner),
    )


async def _seed_dormant_runtime(session_factory) -> None:
    now = datetime.now(timezone.utc) - timedelta(seconds=1)
    async with session_factory() as session:
        await ensure_tenant_website_scope(session)
        owner = StaffUser(
            display_name="Owner",
            status="active",
            roles=["owner"],
            primary_role="owner",
            telegram_id=90001,
        )
        await add_tenant_members(session, owner)
        session.add(
            CommunicationRuntimeState(
                channel="telegram",
                mode="off",
                status="disabled",
                instance_id="communications-worker",
                heartbeat_at=now,
                control_updated_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


def _event(
    sequence: int,
    *,
    status: str,
    created_at: datetime,
) -> IntegrationOutboxEvent:
    return IntegrationOutboxEvent(
        event_id=f"{sequence:032x}",
        event_type=INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
        schema_version=1,
        aggregate_type="order",
        aggregate_id=str(sequence),
        deduplication_key=f"installation-operator:{sequence}",
        payload={},
        status=status,
        attempts=1 if status != "pending" else 0,
        available_at=created_at,
        occurred_at=created_at,
        published_at=created_at if status == "published" else None,
        created_at=created_at,
        updated_at=created_at,
    )


def _terminal_delivery(
    sequence: int,
    *,
    event_id: str,
    status: str,
    now: datetime,
) -> CommunicationDelivery:
    sent = status == "sent"
    return CommunicationDelivery(
        delivery_id=f"{sequence + 100:032x}",
        event_id=event_id,
        channel="telegram",
        recipient_key="staff:owner",
        destination="90001",
        template_key=INSTALLATION_ESTIMATE_TEMPLATE_KEY,
        template_version=1,
        render_context={},
        status=status,
        attempts=1,
        max_attempts=3,
        available_at=now,
        provider_message_id="provider-ack" if sent else None,
        sent_at=now if sent else None,
        finished_at=now,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_enable_sets_once_and_reuses_the_database_activation_watermark(
    operator_session_factory,
    allow_sqlite_operator_checks,
):
    await _seed_dormant_runtime(operator_session_factory)
    config = _runtime_config()

    first = await run_command(
        "enable",
        session_factory=operator_session_factory,
        config=config,
        bot_token="valid-token",
        runtime_locks_enabled=True,
    )
    assert first["runtime_mode"] == "all"
    assert first["control_revision"] == 1
    assert first["owner_recipient_count"] == 1
    first_watermark = first["activation_watermark"]

    disabled = await run_command(
        "off",
        session_factory=operator_session_factory,
        config=replace(config, enabled=False, allow_all_mode=False),
        bot_token=None,
        runtime_locks_enabled=False,
        off_wait_seconds=0,
    )
    assert disabled["drained"] is True
    assert disabled["runtime_mode"] == "off"
    assert disabled["activation_watermark"] is not None

    second = await run_command(
        "enable",
        session_factory=operator_session_factory,
        config=config,
        bot_token="valid-token",
        runtime_locks_enabled=True,
    )
    assert second["control_revision"] == 3
    assert second["activation_watermark"] == first_watermark

    async with operator_session_factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert state is not None
        assert state.mode == "all"
        assert state.installation_estimate_watermark_at is not None


@pytest.mark.asyncio
async def test_canary_profile_can_plan_and_status_but_cannot_enable(
    operator_session_factory,
    allow_sqlite_operator_checks,
):
    await _seed_dormant_runtime(operator_session_factory)
    canary_config = _runtime_config(allow_all_mode=False)

    for mode in ("plan", "status"):
        result = await run_command(
            mode,
            session_factory=operator_session_factory,
            config=canary_config,
            bot_token="valid-token",
            runtime_locks_enabled=True,
        )
        assert result["profile"] == "canary"
        assert "communications_active_profile_required" in result["blockers"]

    dormant = await run_command(
        "plan",
        session_factory=operator_session_factory,
        config=replace(
            canary_config,
            enabled=False,
            allow_all_mode=False,
        ),
        bot_token="valid-token",
        runtime_locks_enabled=True,
    )
    assert dormant["profile"] == "dormant"
    assert "communications_active_profile_required" in dormant["blockers"]

    with pytest.raises(
        InstallationNotificationControlRejected,
        match="communications_active_profile_required",
    ):
        await run_command(
            "enable",
            session_factory=operator_session_factory,
            config=canary_config,
            bot_token="valid-token",
            runtime_locks_enabled=True,
        )

    emergency = await run_command(
        "off",
        session_factory=operator_session_factory,
        config=object(),
        bot_token=None,
        runtime_locks_enabled=False,
        off_wait_seconds=0,
    )
    assert emergency["runtime_mode"] == "off"
    assert emergency["drained"] is True


@pytest.mark.asyncio
async def test_status_has_fixed_aggregate_buckets_and_blocks_unsafe_backlog(
    operator_session_factory,
    allow_sqlite_operator_checks,
):
    await _seed_dormant_runtime(operator_session_factory)
    now = datetime.now(timezone.utc) - timedelta(seconds=1)
    pending = _event(1, status="pending", created_at=now)
    published_sent = _event(2, status="published", created_at=now)
    published_dead = _event(3, status="published", created_at=now)
    dead = _event(4, status="dead", created_at=now)
    sent_delivery = _terminal_delivery(
        1,
        event_id=published_sent.event_id,
        status="sent",
        now=now,
    )
    dead_delivery = _terminal_delivery(
        2,
        event_id=published_dead.event_id,
        status="dead",
        now=now,
    )
    queued_on_dead_outbox = CommunicationDelivery(
        delivery_id=f"{203:032x}",
        event_id=dead.event_id,
        channel="telegram",
        recipient_key="staff:owner",
        destination="90001",
        template_key=INSTALLATION_ESTIMATE_TEMPLATE_KEY,
        template_version=1,
        render_context={},
        status="queued",
        attempts=0,
        max_attempts=3,
        available_at=now,
        created_at=now,
        updated_at=now,
    )
    async with operator_session_factory() as session:
        session.add_all(
            [
                pending,
                published_sent,
                published_dead,
                dead,
                sent_delivery,
                dead_delivery,
                queued_on_dead_outbox,
                CommunicationDeliveryAttempt(
                    delivery_id=sent_delivery.delivery_id,
                    attempt_no=1,
                    started_at=now,
                    finished_at=now,
                    outcome="sent",
                ),
                CommunicationDeliveryAttempt(
                    delivery_id=dead_delivery.delivery_id,
                    attempt_no=1,
                    started_at=now,
                    finished_at=now,
                    outcome="dead",
                    error_category="provider",
                    error_code="provider_ack_unknown",
                    ambiguous=True,
                ),
                CommunicationDeliveryAttempt(
                    delivery_id=dead_delivery.delivery_id,
                    attempt_no=2,
                    started_at=now,
                    outcome="running",
                ),
                CommunicationDeliveryAttempt(
                    delivery_id=dead_delivery.delivery_id,
                    attempt_no=3,
                    started_at=now,
                    finished_at=now,
                    outcome="dead",
                    error_category="provider",
                    error_code="provider_ack_unknown_again",
                    ambiguous=True,
                ),
            ]
        )
        await session.commit()

    status = await run_command(
        "status",
        session_factory=operator_session_factory,
        config=_runtime_config(),
        bot_token="valid-token",
        runtime_locks_enabled=True,
    )
    assert status["outbox_status_counts"] == {
        "pending": 1,
        "processing": 0,
        "published": 2,
        "dead": 1,
    }
    assert status["delivery_status_counts"] == {
        "queued": 1,
        "running": 0,
        "retry": 0,
        "sent": 1,
        "dead": 1,
        "canceled": 0,
    }
    assert status["attempt_outcome_counts"] == {
        "running": 1,
        "sent": 1,
        "retry": 0,
        "dead": 2,
        "canceled": 0,
    }
    assert status["provider_ack_count"] == 1
    assert status["ambiguous_nonterminal_count"] == 0
    assert status["ambiguous_terminal_count"] == 2
    assert status["ambiguous_total_count"] == 2
    assert status["backlog_count"] == 2
    assert status["running_count"] == 1
    assert "installation_backlog_not_reconciled" in status["blockers"]
    assert "installation_delivery_running" in status["blockers"]
    assert (
        "installation_ambiguous_outcomes_unreconciled"
        not in status["blockers"]
    )
    assert "90001" not in json.dumps(status)

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

    async with operator_session_factory() as session:
        state = await session.get(CommunicationRuntimeState, "telegram")
        assert state is not None
        assert state.mode == "off"
        assert state.control_revision == 0
        assert state.installation_estimate_watermark_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "expected_blocker"),
    [
        ("wrong_role", "app_role_not_primary"),
        ("read_only", "database_not_writable_primary"),
        ("locks_disabled", "runtime_database_locks_required"),
        ("lock_zero", "communications_runtime_owner_count_invalid"),
        ("lock_two", "communications_runtime_owner_count_invalid"),
        ("missing_token", "telegram_bot_token_missing"),
        ("stale_heartbeat", "communications_runtime_owner_not_fresh"),
        ("mode_not_off", "communications_runtime_mode_not_off"),
        ("runtime_not_dormant", "communications_runtime_not_dormant"),
        ("future_watermark", "installation_activation_watermark_invalid"),
    ],
)
async def test_enable_rejects_each_safety_gate_without_mutating_control(
    operator_session_factory,
    allow_sqlite_operator_checks,
    monkeypatch,
    case,
    expected_blocker,
):
    await _seed_dormant_runtime(operator_session_factory)
    config = _runtime_config()
    token = "valid-token"
    locks_enabled = True

    if case == "wrong_role":
        config = replace(config, app_role="replica")
    elif case == "read_only":
        async def read_only(cls, session):
            return "database_not_writable_primary"

        monkeypatch.setattr(
            InstallationNotificationOperations,
            "_database_primary_blocker",
            classmethod(read_only),
        )
    elif case == "locks_disabled":
        locks_enabled = False
    elif case in {"lock_zero", "lock_two"}:
        owner_count = 0 if case == "lock_zero" else 2

        async def lock_owners(cls, session, *, lock_name):
            return owner_count

        monkeypatch.setattr(
            InstallationNotificationOperations,
            "_runtime_lock_owner_count",
            classmethod(lock_owners),
        )
    elif case == "missing_token":
        token = ""
    else:
        async with operator_session_factory() as session:
            state = await session.get(CommunicationRuntimeState, "telegram")
            assert state is not None
            if case == "stale_heartbeat":
                state.heartbeat_at = datetime.now(timezone.utc) - timedelta(
                    minutes=10
                )
            elif case == "mode_not_off":
                state.mode = "canary"
                state.canary_run_id = "123e4567-e89b-42d3-a456-426614174000"
            elif case == "runtime_not_dormant":
                state.status = "running"
            elif case == "future_watermark":
                state.installation_estimate_watermark_at = (
                    datetime.now(timezone.utc) + timedelta(days=1)
                )
            await session.commit()

    async with operator_session_factory() as session:
        before = await session.get(CommunicationRuntimeState, "telegram")
        assert before is not None
        before_control = (
            before.mode,
            before.canary_run_id,
            before.control_revision,
            before.installation_estimate_watermark_at,
        )

    plan = await run_command(
        "plan",
        session_factory=operator_session_factory,
        config=config,
        bot_token=token,
        runtime_locks_enabled=locks_enabled,
    )
    assert expected_blocker in plan["blockers"]
    with pytest.raises(
        InstallationNotificationControlRejected,
        match=expected_blocker,
    ):
        await run_command(
            "enable",
            session_factory=operator_session_factory,
            config=config,
            bot_token=token,
            runtime_locks_enabled=locks_enabled,
        )

    async with operator_session_factory() as session:
        after = await session.get(CommunicationRuntimeState, "telegram")
        assert after is not None
        assert (
            after.mode,
            after.canary_run_id,
            after.control_revision,
            after.installation_estimate_watermark_at,
        ) == before_control


@pytest.mark.asyncio
async def test_enable_rejects_non_postgresql_even_when_other_inputs_are_safe(
    operator_session_factory,
):
    await _seed_dormant_runtime(operator_session_factory)
    plan = await run_command(
        "plan",
        session_factory=operator_session_factory,
        config=_runtime_config(),
        bot_token="valid-token",
        runtime_locks_enabled=True,
    )
    assert "database_dialect_not_postgresql" in plan["blockers"]

    with pytest.raises(
        InstallationNotificationControlRejected,
        match="database_dialect_not_postgresql",
    ):
        await run_command(
            "enable",
            session_factory=operator_session_factory,
            config=_runtime_config(),
            bot_token="valid-token",
            runtime_locks_enabled=True,
        )


@pytest.mark.asyncio
async def test_enable_reports_terminal_ambiguity_without_retrying_or_blocking(
    operator_session_factory,
    allow_sqlite_operator_checks,
):
    await _seed_dormant_runtime(operator_session_factory)
    now = datetime.now(timezone.utc) - timedelta(seconds=1)
    event = _event(40, status="published", created_at=now)
    delivery = _terminal_delivery(
        40,
        event_id=event.event_id,
        status="dead",
        now=now,
    )
    async with operator_session_factory() as session:
        session.add_all(
            [
                event,
                delivery,
                CommunicationDeliveryAttempt(
                    delivery_id=delivery.delivery_id,
                    attempt_no=1,
                    started_at=now,
                    finished_at=now,
                    outcome="dead",
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
    assert plan["backlog_count"] == 0
    assert plan["running_count"] == 0
    assert plan["ambiguous_nonterminal_count"] == 0
    assert plan["ambiguous_terminal_count"] == 1
    assert plan["ambiguous_total_count"] == 1
    assert (
        "installation_ambiguous_outcomes_unreconciled"
        not in plan["blockers"]
    )

    enabled = await run_command(
        "enable",
        session_factory=operator_session_factory,
        config=_runtime_config(),
        bot_token="valid-token",
        runtime_locks_enabled=True,
    )
    assert enabled["runtime_mode"] == "all"
    assert enabled["ambiguous_terminal_count"] == 1


def test_cli_accepts_only_the_four_typed_modes():
    parser = build_parser()
    for flag in ("--plan", "--enable", "--status", "--off"):
        assert vars(parser.parse_args([flag]))[flag.removeprefix("--")] is True
    with pytest.raises(SystemExit):
        parser.parse_args(["--plan", "--event-type", "anything"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--plan", "--enable"])


def test_cli_reports_incomplete_off_drain_as_safe_nonzero_result(
    monkeypatch,
    capsys,
):
    async def incomplete_off(mode):
        assert mode == "off"
        return {
            "command": "off",
            "drained": False,
            "runtime_mode": "off",
            "runtime_status": "stopping",
            "running_delivery_count": 1,
            "ambiguous_total_count": 1,
        }

    monkeypatch.setattr(command_module, "run_command", incomplete_off)

    assert command_module.main(["--off"]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "ok": False,
        "error_code": "installation_notification_drain_incomplete",
        "command": "off",
        "drained": False,
        "runtime_mode": "off",
        "runtime_status": "stopping",
        "running_delivery_count": 1,
        "ambiguous_total_count": 1,
    }


def test_cli_redacts_unexpected_exception_details(monkeypatch, capsys):
    secret = "bot-token-and-destination-90001"

    async def fail_with_secret(mode):
        raise RuntimeError(secret)

    monkeypatch.setattr(command_module, "run_command", fail_with_secret)

    assert command_module.main(["--status"]) == 1
    output = capsys.readouterr().out
    assert secret not in output
    assert json.loads(output) == {
        "ok": False,
        "error_code": "installation_notification_command_failed",
    }
