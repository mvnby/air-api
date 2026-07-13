from __future__ import annotations

import json

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import (
    CommunicationDelivery,
    CommunicationRuntimeState,
    IntegrationOutboxEvent,
    StaffUser,
)
from scripts import communications_telegram_canary as canary_cli
from services.communications.canary import CommunicationsTelegramCanary
from services.communications.runtime_state import (
    CommunicationRuntimeControlConflict,
    CommunicationRuntimeMode,
    CommunicationRuntimeStateService,
)


RUN_ID_A = "123e4567-e89b-42d3-a456-426614174000"


@pytest.fixture
async def canary_session_factory(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'canary-runtime.sqlite3'}"
    )
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


@pytest.mark.asyncio
async def test_canary_cli_execute_atomically_arms_and_replay_never_rearms(
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
    assert first["runtime_armed"] is True
    assert first["sent_directly"] is False
    assert first["recipient_keys"] == ["staff:1", "staff:2"]
    assert replay["event_id"] == first["event_id"]
    assert replay["accepted"] is False
    assert replay["created"] is False
    assert replay["replay"] is True
    assert replay["execution_result"] == "replay_pending"
    assert replay["runtime_armed"] is False
    assert replay_plan["existing"] is True
    assert replay_plan["existing_status"] == "pending"
    assert replay_plan["execute_would_create"] is False
    assert replay_plan["will_enqueue"] is False
    serialized_first = json.dumps(first)
    assert '"101"' not in serialized_first
    assert '"202"' not in serialized_first
    assert "destination" not in serialized_first

    async with canary_session_factory() as session:
        runtime = await session.get(CommunicationRuntimeState, "telegram")
        assert runtime is not None
        assert runtime.mode == CommunicationRuntimeMode.CANARY.value
        assert runtime.canary_run_id == RUN_ID_A
        assert runtime.control_revision == 1
        assert (
            await session.execute(select(func.count(IntegrationOutboxEvent.event_id)))
        ).scalar_one() == 1
        assert (
            await session.execute(select(func.count(CommunicationDelivery.delivery_id)))
        ).scalar_one() == 0

    disabled = await canary_cli.run_command(
        "off",
        run_id=None,
        session_factory=canary_session_factory,
        app_role="primary",
        bot_token=None,
    )
    replay_after_off = await canary_cli.run_command(
        "execute",
        run_id=RUN_ID_A,
        session_factory=canary_session_factory,
        app_role="primary",
        bot_token="12345:private-token",
    )

    assert disabled == {
        "mode": "off",
        "previous_mode": "canary",
        "previous_canary_run_id": RUN_ID_A,
        "control_revision": 2,
    }
    assert replay_after_off["event_id"] == first["event_id"]
    assert replay_after_off["replay"] is True
    assert replay_after_off["runtime_armed"] is False

    async with canary_session_factory() as session:
        runtime = await session.get(CommunicationRuntimeState, "telegram")
        assert runtime is not None
        assert runtime.mode == CommunicationRuntimeMode.OFF.value
        assert runtime.canary_run_id is None
        assert runtime.control_revision == 2


@pytest.mark.asyncio
async def test_canary_execute_rolls_back_event_when_runtime_arm_fails(
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
        await CommunicationRuntimeStateService.read_control(
            session,
            channel="telegram",
        )
        await session.commit()

    original_arm = CommunicationRuntimeStateService.arm_canary_from_off

    async def fail_after_arm(session, *, channel: str, run_id: str):
        await original_arm(session, channel=channel, run_id=run_id)
        raise CommunicationRuntimeControlConflict("injected_arm_failure")

    monkeypatch.setattr(
        CommunicationRuntimeStateService,
        "arm_canary_from_off",
        staticmethod(fail_after_arm),
    )

    with pytest.raises(canary_cli.CanaryCommandRejected) as rejected:
        await canary_cli.run_command(
            "execute",
            run_id=RUN_ID_A,
            session_factory=canary_session_factory,
            app_role="primary",
            bot_token="12345:private-token",
        )
    assert rejected.value.error_code == "injected_arm_failure"

    async with canary_session_factory() as session:
        assert (
            await session.execute(select(func.count(IntegrationOutboxEvent.event_id)))
        ).scalar_one() == 0
        runtime = await session.get(CommunicationRuntimeState, "telegram")
        assert runtime is not None
        assert runtime.mode == CommunicationRuntimeMode.OFF.value
        assert runtime.canary_run_id is None
        assert runtime.control_revision == 0


@pytest.mark.asyncio
async def test_canary_off_needs_no_run_id_token_or_owner_recipients(
    canary_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        CommunicationsTelegramCanary,
        "assert_primary_writable_database",
        staticmethod(_allow_test_database),
    )
    async with canary_session_factory() as session:
        control = await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=CommunicationRuntimeMode.CANARY,
            canary_run_id=RUN_ID_A,
        )
        await session.commit()
        assert control.control_revision == 1
        assert (
            await session.execute(select(func.count(StaffUser.id)))
        ).scalar_one() == 0

    disabled = await canary_cli.run_command(
        "off",
        run_id=None,
        session_factory=canary_session_factory,
        app_role="primary",
        bot_token=None,
    )

    assert disabled == {
        "mode": "off",
        "previous_mode": "canary",
        "previous_canary_run_id": RUN_ID_A,
        "control_revision": 2,
    }
    async with canary_session_factory() as session:
        runtime = await session.get(CommunicationRuntimeState, "telegram")
        assert runtime is not None
        assert runtime.mode == CommunicationRuntimeMode.OFF.value
        assert runtime.canary_run_id is None
        assert runtime.control_revision == 2


def test_canary_cli_main_allows_off_without_run_id(monkeypatch, capsys):
    async def succeed(mode, *, run_id):
        assert mode == "off"
        assert run_id is None
        return {
            "mode": "off",
            "previous_mode": "off",
            "previous_canary_run_id": None,
            "control_revision": 0,
        }

    monkeypatch.setattr(canary_cli, "run_command", succeed)

    assert canary_cli.main(["--off"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "mode": "off",
        "previous_mode": "off",
        "previous_canary_run_id": None,
        "control_revision": 0,
    }
