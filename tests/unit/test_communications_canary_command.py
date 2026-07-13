from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import CommunicationDelivery, IntegrationOutboxEvent, StaffUser
from scripts import communications_telegram_canary as canary_cli
from services.communications.canary import (
    CANARY_MAX_ATTEMPTS,
    CommunicationsTelegramCanary,
)
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.template_registry import TELEGRAM_CANARY_TEMPLATE_KEY


RUN_ID_A = "123e4567-e89b-42d3-a456-426614174000"
RUN_ID_B = "123e4567-e89b-42d3-b456-426614174001"


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


def _owner(name: str, telegram_id: int) -> StaffUser:
    return StaffUser(
        display_name=name,
        status="active",
        roles=["owner"],
        primary_role="owner",
        telegram_id=telegram_id,
    )


async def _allow_test_database(_session: AsyncSession) -> None:
    return None


def _delivery_for_status(
    event: IntegrationOutboxEvent,
    *,
    recipient_key: str,
    destination: str,
    status: str,
    marker: str,
    now: datetime,
) -> CommunicationDelivery:
    attempts = 0 if status == "queued" else 1
    terminal = status in {"sent", "dead", "canceled"}
    running = status == "running"
    return CommunicationDelivery(
        delivery_id=marker * 32,
        event_id=event.event_id,
        channel="telegram",
        recipient_key=recipient_key,
        destination=destination,
        template_key=TELEGRAM_CANARY_TEMPLATE_KEY,
        template_version=1,
        render_context=event.payload,
        status=status,
        priority=0,
        attempts=attempts,
        max_attempts=1,
        available_at=now,
        worker_id="canary-worker" if running else None,
        lease_token="lease-token" if running else None,
        lease_expires_at=now + timedelta(minutes=1) if running else None,
        provider_message_id=f"ack-{marker}" if status == "sent" else None,
        sent_at=now if status == "sent" else None,
        finished_at=now if terminal else None,
        created_at=now,
        updated_at=now,
    )


def test_canary_runtime_gate_requires_literal_primary_role_and_real_token():
    CommunicationsTelegramCanary.validate_runtime(
        app_role="primary",
        bot_token="12345:test-token",
    )

    for role in ("active", "standby", "", None):
        with pytest.raises(CommunicationsCanarySafetyError) as exc_info:
            CommunicationsTelegramCanary.validate_runtime(
                app_role=role,
                bot_token="12345:test-token",
            )
        assert exc_info.value.error_code == "app_role_not_primary"

    for token in ("", None, "0:disabled-bot-token"):
        with pytest.raises(CommunicationsCanarySafetyError) as exc_info:
            CommunicationsTelegramCanary.validate_runtime(
                app_role="primary",
                bot_token=token,
            )
        assert exc_info.value.error_code == "telegram_bot_token_missing"


@pytest.mark.asyncio
async def test_canary_command_preserves_only_safe_gate_code(canary_session_factory):
    with pytest.raises(canary_cli.CanaryCommandRejected) as exc_info:
        await canary_cli.run_command(
            "plan",
            run_id=RUN_ID_A,
            session_factory=canary_session_factory,
            app_role="standby",
            bot_token="12345:private-token",
        )
    assert exc_info.value.error_code == "app_role_not_primary"

    with pytest.raises(canary_cli.CanaryCommandRejected) as invalid_run:
        await canary_cli.run_command(
            "status",
            run_id="release-candidate",
            session_factory=canary_session_factory,
            app_role="primary",
            bot_token="12345:private-token",
        )
    assert invalid_run.value.error_code == "canary_run_id_invalid"


@pytest.mark.asyncio
async def test_canary_database_gate_requires_writable_postgresql():
    non_postgres = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    )
    with pytest.raises(CommunicationsCanarySafetyError) as dialect_error:
        await CommunicationsTelegramCanary.assert_primary_writable_database(
            non_postgres
        )
    assert dialect_error.value.error_code == "database_dialect_not_postgresql"

    writable = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar=lambda: False),
                SimpleNamespace(scalar=lambda: "off"),
            ]
        ),
    )
    await CommunicationsTelegramCanary.assert_primary_writable_database(writable)

    read_only = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar=lambda: False),
                SimpleNamespace(scalar=lambda: "on"),
            ]
        ),
    )
    with pytest.raises(CommunicationsCanarySafetyError) as writable_error:
        await CommunicationsTelegramCanary.assert_primary_writable_database(read_only)
    assert writable_error.value.error_code == "database_not_writable_primary"


@pytest.mark.asyncio
async def test_canary_producer_is_transaction_owned_and_idempotent(
    canary_session_factory,
):
    event_id = CommunicationsTelegramCanary.event_id(RUN_ID_A)
    recipient_keys = ("staff:1", "staff:2")

    async with canary_session_factory() as session:
        session.add_all([_owner("Owner One", 101), _owner("Owner Two", 202)])
        await session.commit()
        first = await CommunicationsTelegramCanary.enqueue(
            session,
            run_id=RUN_ID_A,
            recipient_keys=recipient_keys,
        )
        assert first.created is True
        assert first.event.event_id == event_id
        assert await session.get(IntegrationOutboxEvent, event_id) is not None
        await session.rollback()

    async with canary_session_factory() as session:
        assert await session.get(IntegrationOutboxEvent, event_id) is None
        committed = await CommunicationsTelegramCanary.enqueue(
            session,
            run_id=RUN_ID_A,
            recipient_keys=recipient_keys,
        )
        await session.commit()
        assert committed.event.event_id == event_id

    async with canary_session_factory() as session:
        replay = await CommunicationsTelegramCanary.enqueue(
            session,
            run_id=RUN_ID_A,
            recipient_keys=recipient_keys,
            occurred_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        await session.commit()

        assert replay.event.event_id == event_id
        assert replay.created is False
        assert replay.event.max_attempts == CANARY_MAX_ATTEMPTS == 1
        assert replay.event.payload == {
            "run_id": RUN_ID_A,
            "recipient_keys": ["staff:1", "staff:2"],
        }
        assert (
            await session.execute(select(func.count(IntegrationOutboxEvent.event_id)))
        ).scalar_one() == 1
        assert (
            await session.execute(select(func.count(CommunicationDelivery.delivery_id)))
        ).scalar_one() == 0

        independent = await CommunicationsTelegramCanary.enqueue(
            session,
            run_id=RUN_ID_B,
            recipient_keys=recipient_keys,
        )
        await session.commit()
        assert independent.created is True
        assert independent.event.event_id != event_id
        assert independent.event.aggregate_id == RUN_ID_B
        assert independent.event.deduplication_key != replay.event.deduplication_key
        assert independent.event.idempotency_key != replay.event.idempotency_key
        assert (
            await session.execute(select(func.count(IntegrationOutboxEvent.event_id)))
        ).scalar_one() == 2


@pytest.mark.asyncio
async def test_canary_producer_rejects_existing_event_with_retry_budget_drift(
    canary_session_factory,
):
    async with canary_session_factory() as session:
        session.add_all([_owner("Owner One", 101), _owner("Owner Two", 202)])
        await session.commit()
        result = await CommunicationsTelegramCanary.enqueue(
            session,
            run_id=RUN_ID_A,
            recipient_keys=("staff:1", "staff:2"),
        )
        await session.commit()
        result.event.max_attempts = 8
        session.add(result.event)
        await session.commit()

    async with canary_session_factory() as session:
        with pytest.raises(CommunicationsCanarySafetyError) as exc_info:
            await CommunicationsTelegramCanary.enqueue(
                session,
                run_id=RUN_ID_A,
                recipient_keys=("staff:1", "staff:2"),
            )
        assert exc_info.value.error_code == "canary_event_invalid"
        await session.rollback()


@pytest.mark.asyncio
async def test_canary_cli_execute_only_enqueues_and_replays_idempotently(
    canary_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        CommunicationsTelegramCanary,
        "assert_primary_writable_database",
        staticmethod(_allow_test_database),
    )
    async with canary_session_factory() as session:
        session.add_all([_owner("Owner One", 101), _owner("Owner Two", 202)])
        await session.commit()

    planned = await canary_cli.run_command(
        "plan",
        run_id=RUN_ID_A,
        session_factory=canary_session_factory,
        app_role="primary",
        bot_token="12345:private-token",
    )
    first = await canary_cli.run_command(
        "execute",
        run_id=RUN_ID_A,
        session_factory=canary_session_factory,
        app_role="primary",
        bot_token="12345:private-token",
    )
    replay = await canary_cli.run_command(
        "execute",
        run_id=RUN_ID_A,
        session_factory=canary_session_factory,
        app_role="primary",
        bot_token="12345:private-token",
    )
    replay_plan = await canary_cli.run_command(
        "plan",
        run_id=RUN_ID_A,
        session_factory=canary_session_factory,
        app_role="primary",
        bot_token="12345:private-token",
    )

    assert planned["run_id"] == RUN_ID_A
    assert planned["existing"] is False
    assert planned["execute_would_create"] is True
    assert planned["will_enqueue"] is False
    assert first["accepted"] is True
    assert first["created"] is True
    assert first["replay"] is False
    assert first["execution_result"] == "created"
    assert first["sent_directly"] is False
    assert first["recipient_keys"] == ["staff:1", "staff:2"]
    assert replay["event_id"] == first["event_id"]
    assert replay["accepted"] is False
    assert replay["created"] is False
    assert replay["replay"] is True
    assert replay["execution_result"] == "replay_pending"
    assert replay_plan["existing"] is True
    assert replay_plan["existing_status"] == "pending"
    assert replay_plan["execute_would_create"] is False
    assert replay_plan["will_enqueue"] is False
    serialized_first = json.dumps(first)
    assert '"101"' not in serialized_first
    assert '"202"' not in serialized_first
    assert "destination" not in serialized_first

    async with canary_session_factory() as session:
        assert (
            await session.execute(select(func.count(IntegrationOutboxEvent.event_id)))
        ).scalar_one() == 1
        assert (
            await session.execute(select(func.count(CommunicationDelivery.delivery_id)))
        ).scalar_one() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "event_status",
        "delivery_statuses",
        "expected_result",
        "expected_lifecycle",
        "expected_outcome",
    ),
    [
        ("published", ("sent", "sent"), "replay_terminal", "terminal", "success"),
        ("dead", (), "replay_terminal", "terminal", "dead"),
        ("published", ("sent", "dead"), "replay_terminal", "terminal", "partial"),
        ("processing", (), "replay_pending", "pending", None),
        ("published", ("running", "queued"), "replay_pending", "pending", None),
        ("published", ("sent", "queued"), "replay_pending", "pending", None),
        ("published", ("sent",), "replay_ambiguous", "ambiguous", None),
    ],
)
async def test_canary_execute_replay_classifies_history_without_resurrection(
    canary_session_factory,
    monkeypatch,
    event_status,
    delivery_statuses,
    expected_result,
    expected_lifecycle,
    expected_outcome,
):
    monkeypatch.setattr(
        CommunicationsTelegramCanary,
        "assert_primary_writable_database",
        staticmethod(_allow_test_database),
    )
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    async with canary_session_factory() as session:
        session.add_all([_owner("Owner One", 101), _owner("Owner Two", 202)])
        await session.commit()
        result = await CommunicationsTelegramCanary.enqueue(
            session,
            run_id=RUN_ID_A,
            recipient_keys=("staff:1", "staff:2"),
            occurred_at=now,
        )
        event = result.event
        event.status = event_status
        event.attempts = 1 if event_status != "pending" else 0
        if event_status == "published":
            event.published_at = now
        if event_status == "processing":
            event.worker_id = "dispatcher"
            event.lease_token = None
            event.lease_expires_at = None
        session.add(event)
        for index, status in enumerate(delivery_statuses):
            session.add(
                _delivery_for_status(
                    event,
                    recipient_key=f"staff:{index + 1}",
                    destination=str(101 + index * 101),
                    status=status,
                    marker=chr(ord("e") + index),
                    now=now,
                )
            )
        await session.commit()

        before_events = (
            await session.execute(select(func.count(IntegrationOutboxEvent.event_id)))
        ).scalar_one()
        before_deliveries = (
            await session.execute(select(func.count(CommunicationDelivery.delivery_id)))
        ).scalar_one()

    replay = await canary_cli.run_command(
        "execute",
        run_id=RUN_ID_A,
        session_factory=canary_session_factory,
        app_role="primary",
        bot_token="12345:private-token",
    )

    assert replay["execution_result"] == expected_result
    assert replay["lifecycle"] == expected_lifecycle
    assert replay["terminal_outcome"] == expected_outcome
    assert replay["accepted"] is False
    assert replay["created"] is False
    assert replay["replay"] is True

    async with canary_session_factory() as session:
        assert (
            await session.execute(select(func.count(IntegrationOutboxEvent.event_id)))
        ).scalar_one() == before_events
        assert (
            await session.execute(select(func.count(CommunicationDelivery.delivery_id)))
        ).scalar_one() == before_deliveries


@pytest.mark.asyncio
async def test_canary_history_survives_owner_change_and_new_run_uses_new_snapshot(
    canary_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        CommunicationsTelegramCanary,
        "assert_primary_writable_database",
        staticmethod(_allow_test_database),
    )
    async with canary_session_factory() as session:
        first_owner = _owner("Owner One", 101)
        second_owner = _owner("Owner Two", 202)
        session.add_all([first_owner, second_owner])
        await session.commit()

    first = await canary_cli.run_command(
        "execute",
        run_id=RUN_ID_A,
        session_factory=canary_session_factory,
        app_role="primary",
        bot_token="12345:private-token",
    )

    async with canary_session_factory() as session:
        first_owner = await session.get(StaffUser, 1)
        assert first_owner is not None
        first_owner.primary_role = "manager"
        first_owner.roles = ["manager"]
        session.add(first_owner)
        session.add(_owner("Replacement Owner", 303))
        await session.commit()

    historical = await canary_cli.run_command(
        "status",
        run_id=RUN_ID_A,
        session_factory=canary_session_factory,
        app_role="primary",
        bot_token="12345:private-token",
    )
    assert historical["found"] is True
    assert historical["event_id"] == first["event_id"]
    assert historical["recipient_keys"] == ["staff:1", "staff:2"]

    with pytest.raises(canary_cli.CanaryCommandRejected) as conflict:
        await canary_cli.run_command(
            "execute",
            run_id=RUN_ID_A,
            session_factory=canary_session_factory,
            app_role="primary",
            bot_token="12345:private-token",
        )
    assert conflict.value.error_code == "canary_snapshot_conflict"

    second = await canary_cli.run_command(
        "execute",
        run_id=RUN_ID_B,
        session_factory=canary_session_factory,
        app_role="primary",
        bot_token="12345:private-token",
    )
    assert second["event_id"] != first["event_id"]
    assert second["recipient_keys"] == ["staff:2", "staff:3"]

    still_historical = await canary_cli.run_command(
        "status",
        run_id=RUN_ID_A,
        session_factory=canary_session_factory,
        app_role="primary",
        bot_token="12345:private-token",
    )
    assert still_historical["event_id"] == first["event_id"]
    assert still_historical["recipient_keys"] == ["staff:1", "staff:2"]


@pytest.mark.asyncio
async def test_canary_status_output_excludes_destinations_secrets_and_raw_ack(
    canary_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        CommunicationsTelegramCanary,
        "assert_primary_writable_database",
        staticmethod(_allow_test_database),
    )
    token = "12345:private-bot-token"
    now = datetime(2026, 7, 13, 11, 0, tzinfo=timezone.utc)
    async with canary_session_factory() as session:
        session.add_all(
            [
                _owner("Private Owner One", 987654321),
                _owner("Private Owner Two", 987654322),
            ]
        )
        await session.flush()
        result = await CommunicationsTelegramCanary.enqueue(
            session,
            run_id=RUN_ID_A,
            recipient_keys=("staff:1", "staff:2"),
            occurred_at=now,
        )
        event = result.event
        event.status = "published"
        event.attempts = 1
        event.published_at = now
        event.last_error_message = "private database detail"
        session.add(event)
        session.add(
            CommunicationDelivery(
                delivery_id="b" * 32,
                event_id=event.event_id,
                channel="telegram",
                recipient_key="staff:1",
                destination="987654321",
                template_key=TELEGRAM_CANARY_TEMPLATE_KEY,
                template_version=1,
                render_context=event.payload,
                status="sent",
                attempts=1,
                max_attempts=1,
                provider_message_id="provider-secret-ack-id",
                last_error_message="private provider detail",
                available_at=now,
                sent_at=now,
                finished_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    status = await canary_cli.run_command(
        "status",
        run_id=RUN_ID_A,
        session_factory=canary_session_factory,
        app_role="primary",
        bot_token=token,
    )
    serialized = json.dumps(status, ensure_ascii=False)

    assert status["found"] is True
    assert status["run_id"] == RUN_ID_A
    assert status["lifecycle"] == "ambiguous"
    assert status["terminal_outcome"] is None
    assert status["deliveries"][0]["provider_ack"] is True
    assert status["deliveries"][0]["recipient_key"] == "staff:1"
    for secret in (
        token,
        "987654321",
        "Private Owner One",
        "provider-secret-ack-id",
        "private database detail",
        "private provider detail",
        "destination",
        "provider_message_id",
        "last_error_message",
        "render_context",
        "payload",
    ):
        assert secret not in serialized


def test_canary_cli_accepts_no_destination_or_arbitrary_text_arguments():
    parser = canary_cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["--execute", "--run-id", RUN_ID_A, "--destination", "123"]
        )
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["--execute", "--run-id", RUN_ID_A, "--text", "custom message"]
        )
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--status"])


@pytest.mark.parametrize(
    "run_id",
    [
        "release-candidate",
        "123e4567-e89b-12d3-a456-426614174000",
        "123e4567-e89b-42d3-7456-426614174000",
        RUN_ID_A.upper(),
        "123e4567e89b42d3a456426614174000",
        " 123e4567-e89b-42d3-a456-426614174000 ",
    ],
)
def test_canary_cli_rejects_noncanonical_uuid4_run_ids(run_id):
    with pytest.raises(SystemExit):
        canary_cli.build_parser().parse_args(
            ["--status", "--run-id", run_id]
        )

    with pytest.raises(CommunicationsCanarySafetyError) as exc_info:
        CommunicationsTelegramCanary.normalize_run_id(run_id)
    assert exc_info.value.error_code == "canary_run_id_invalid"


def test_canary_cli_masks_unexpected_exception_text(monkeypatch, capsys):
    async def fail(_mode, *, run_id):
        assert run_id == RUN_ID_A
        raise RuntimeError("postgresql://user:secret@example.invalid/database")

    monkeypatch.setattr(canary_cli, "run_command", fail)
    assert canary_cli.main(["--status", "--run-id", RUN_ID_A]) == 1
    output = capsys.readouterr().out
    assert "secret" not in output
    assert json.loads(output) == {
        "ok": False,
        "error_code": "canary_command_failed",
    }
