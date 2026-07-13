import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import services.communications.runtime as runtime_module
from conftest import TEST_DATABASE_URL
from models import CommunicationRuntimeState
from services.communications.runtime import (
    CommunicationRuntimeConfig,
    CommunicationRuntimeSupervisor,
)
from services.communications.runtime_state import (
    CommunicationRuntimeMode,
    CommunicationRuntimeStateService,
)


async def _wait_until(predicate, *, timeout=3.0):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


@pytest_asyncio.fixture
async def runtime_postgres_engine():
    schema_name = f"communication_runtime_{uuid4().hex}"
    admin_engine = create_async_engine(TEST_DATABASE_URL)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(CommunicationRuntimeState.__table__.create)
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_postgres_runtime_advisory_lock_serializes_two_processes(
    runtime_postgres_engine,
    monkeypatch,
):
    assert runtime_postgres_engine.dialect.name == "postgresql"
    monkeypatch.setattr(
        runtime_module.settings,
        "RUNTIME_DB_LOCKS_ENABLED",
        True,
        raising=False,
    )
    session_factory = sessionmaker(
        bind=runtime_postgres_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        await CommunicationRuntimeStateService.set_mode(
            session,
            channel="telegram",
            mode=CommunicationRuntimeMode.OFF,
        )
        await session.commit()

    lock_name = f"mvn:test:communications-runtime:{uuid4()}"
    base_config = CommunicationRuntimeConfig(
        enabled=True,
        app_role="primary",
        instance_id="runtime-one",
        lock_name=lock_name,
        poll_seconds=0.01,
        heartbeat_seconds=0.05,
        lock_retry_seconds=0.02,
        lock_check_seconds=0.02,
        db_probe_timeout_seconds=0.5,
        fencing_seconds=0.02,
        shutdown_seconds=1,
        provider_timeout_seconds=1,
        provider_close_seconds=0.1,
        lease_seconds=15,
    )
    active = 0
    maximum_active = 0
    started = {"runtime-one": asyncio.Event(), "runtime-two": asyncio.Event()}

    class HoldingPipeline:
        def __init__(self, instance_id):
            self.instance_id = instance_id

        async def run(self, stop_event):
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            started[self.instance_id].set()
            try:
                await stop_event.wait()
            finally:
                active -= 1

    first_stop = asyncio.Event()
    second_stop = asyncio.Event()
    first = CommunicationRuntimeSupervisor(
        config=base_config,
        session_factory=session_factory,
        pipeline_factory=lambda: HoldingPipeline("runtime-one"),
    )
    second_config = replace(base_config, instance_id="runtime-two")
    second = CommunicationRuntimeSupervisor(
        config=second_config,
        session_factory=session_factory,
        pipeline_factory=lambda: HoldingPipeline("runtime-two"),
    )
    first_task = asyncio.create_task(first.run(first_stop))
    second_task = None
    try:
        await asyncio.wait_for(started["runtime-one"].wait(), timeout=2)
        second_task = asyncio.create_task(second.run(second_stop))
        await asyncio.sleep(0.12)
        assert started["runtime-two"].is_set() is False
        assert active == 1

        first_stop.set()
        await asyncio.wait_for(first_task, timeout=2)
        await asyncio.wait_for(started["runtime-two"].wait(), timeout=2)
        assert active == 1
        assert maximum_active == 1

        second_stop.set()
        await asyncio.wait_for(second_task, timeout=2)
        await _wait_until(lambda: active == 0)
        async with session_factory() as session:
            state = await session.get(CommunicationRuntimeState, "telegram")
            assert state is not None
            assert state.instance_id == "runtime-two"
            assert state.status == "stopped"
            assert state.mode == "off"
    finally:
        first_stop.set()
        second_stop.set()
        tasks = [first_task]
        if second_task is not None:
            tasks.append(second_task)
        await asyncio.gather(*tasks, return_exceptions=True)
