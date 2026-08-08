from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import CommunicationWebsiteBacklogOperation
from services.communications.backlog_reconciliation import (
    InstallationEstimateBacklogExecutionBlocked,
)
from services.communications.tenant_website_events import (
    TENANT_WEBSITE_EVENT_TYPES,
)
from services.communications.website_backlog_operation import (
    WebsiteBacklogOperationRunner,
)
from services.communications.website_backlog_reconciliation import (
    WebsiteBacklogManifestItem,
    WebsiteCommunicationBacklogReconciliation,
)


class _HeldRuntimeLock:
    async def is_held(self) -> bool:
        return True


@pytest.fixture
async def backlog_operation_session_factory():
    database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get(
        "DATABASE_URL"
    )
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    assert database_url
    assert "test" in database_url.lower() or environment == "test"

    schema_name = f"website_backlog_c1_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))

    engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            CommunicationWebsiteBacklogOperation.__table__.create
        )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        await admin_engine.dispose()


def _zero_manifest(now: datetime) -> tuple[WebsiteBacklogManifestItem, ...]:
    return tuple(
        WebsiteBacklogManifestItem(
            event_type=event_type,
            cutoff=now - timedelta(days=1),
            expected_count=0,
            disposition="terminal_no_send",
        )
        for event_type in TENANT_WEBSITE_EVENT_TYPES
    )


@pytest.mark.asyncio
async def test_same_operation_failure_is_terminal_before_waiter_can_execute(
    backlog_operation_session_factory,
    monkeypatch,
):
    entered = asyncio.Event()
    release_failure = asyncio.Event()
    reconciliation_calls = 0

    async def fail_first_reconciliation(cls, session, **kwargs):
        nonlocal reconciliation_calls
        reconciliation_calls += 1
        if reconciliation_calls != 1:
            raise AssertionError(
                "a waiting caller executed a shared started operation"
            )
        entered.set()
        await release_failure.wait()
        raise InstallationEstimateBacklogExecutionBlocked(
            "website_backlog_expected_count_changed"
        )

    monkeypatch.setattr(
        WebsiteCommunicationBacklogReconciliation,
        "reconcile_manifest",
        classmethod(fail_first_reconciliation),
    )

    now = datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc)
    operation_id = "77777777-7777-4777-8777-777777777777"
    kwargs = {
        "manifest": _zero_manifest(now),
        "operation_id": operation_id,
        "runtime_lock": _HeldRuntimeLock(),
        "app_role": "primary",
        "now": now,
    }

    first = asyncio.create_task(
        WebsiteBacklogOperationRunner.execute_manifest(
            backlog_operation_session_factory,
            **kwargs,
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=3)
    second = asyncio.create_task(
        WebsiteBacklogOperationRunner.execute_manifest(
            backlog_operation_session_factory,
            **kwargs,
        )
    )
    await asyncio.sleep(0.1)
    assert second.done() is False

    release_failure.set()
    results = await asyncio.wait_for(
        asyncio.gather(first, second, return_exceptions=True),
        timeout=5,
    )

    assert reconciliation_calls == 1
    assert all(
        isinstance(result, InstallationEstimateBacklogExecutionBlocked)
        and result.error_code == "website_backlog_expected_count_changed"
        for result in results
    )
    async with backlog_operation_session_factory() as session:
        operation = await session.get(
            CommunicationWebsiteBacklogOperation,
            operation_id,
        )
    assert operation is not None
    assert operation.state == "blocked"
    assert operation.outcome_code == "website_backlog_expected_count_changed"
