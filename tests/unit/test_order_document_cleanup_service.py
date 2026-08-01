from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import IntegrationOutboxEvent
from models.tenancy import TenantScope
from services.order_document_cleanup_service import (
    ORDER_DOCUMENT_DELETE_REQUESTED_EVENT,
    OrderDocumentCleanupService,
)


TEST_TENANT_SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.fixture
async def cleanup_session_factory(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'document_cleanup.db'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(IntegrationOutboxEvent.__table__.create)

    factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        yield factory
    finally:
        await engine.dispose()


async def _enqueue(cleanup_session_factory, *, file_id: str = "drive-file-1") -> str:
    async with cleanup_session_factory() as session:
        count = await OrderDocumentCleanupService.enqueue_order_documents(
            session,
            order_id=41,
            documents=[SimpleNamespace(id=17, google_file_id=file_id)],
            tenant_scope=TEST_TENANT_SCOPE,
        )
        assert count == 1
        await session.commit()
        event = (
            await session.execute(
                select(IntegrationOutboxEvent).where(
                    IntegrationOutboxEvent.event_type
                    == ORDER_DOCUMENT_DELETE_REQUESTED_EVENT
                )
            )
        ).scalar_one()
        return event.event_id


class _SuccessfulGoogleService:
    def __init__(self):
        self.deleted_file_ids = []

    def delete_file_strict(self, file_id: str) -> None:
        self.deleted_file_ids.append(file_id)


@pytest.mark.asyncio
async def test_cleanup_worker_publishes_event_after_drive_delete(
    cleanup_session_factory,
):
    event_id = await _enqueue(cleanup_session_factory)
    google_service = _SuccessfulGoogleService()
    now = datetime.now(timezone.utc) + timedelta(minutes=1)

    outcome = await OrderDocumentCleanupService.process_next(
        worker_id="test-cleanup-worker",
        session_factory=cleanup_session_factory,
        google_service=google_service,
        now=now,
    )

    assert outcome is not None
    assert outcome.event_id == event_id
    assert outcome.outcome == "deleted"
    assert google_service.deleted_file_ids == ["drive-file-1"]
    async with cleanup_session_factory() as session:
        event = await session.get(IntegrationOutboxEvent, event_id)
        assert event is not None
        assert event.status == "published"
        assert event.attempts == 1
        assert event.published_at is not None
        assert event.worker_id is None
        assert event.lease_token is None


@pytest.mark.asyncio
async def test_cleanup_worker_retries_provider_failure_then_succeeds(
    cleanup_session_factory,
):
    event_id = await _enqueue(cleanup_session_factory, file_id="drive-file-retry")

    class _FailingGoogleService:
        def delete_file_strict(self, _file_id: str) -> None:
            raise RuntimeError("temporary provider failure")

    first_time = datetime.now(timezone.utc) + timedelta(minutes=1)
    first = await OrderDocumentCleanupService.process_next(
        worker_id="test-cleanup-worker",
        session_factory=cleanup_session_factory,
        google_service=_FailingGoogleService(),
        now=first_time,
    )
    assert first is not None
    assert first.outcome == "retry_scheduled"
    assert first.next_attempt_at is not None

    successful_service = _SuccessfulGoogleService()
    second = await OrderDocumentCleanupService.process_next(
        worker_id="test-cleanup-worker",
        session_factory=cleanup_session_factory,
        google_service=successful_service,
        now=first.next_attempt_at + timedelta(seconds=1),
    )
    assert second is not None
    assert second.outcome == "deleted"
    assert second.attempts == 2
    assert successful_service.deleted_file_ids == ["drive-file-retry"]

    async with cleanup_session_factory() as session:
        event = await session.get(IntegrationOutboxEvent, event_id)
        assert event is not None
        assert event.status == "published"
        assert event.attempts == 2


@pytest.mark.asyncio
async def test_cleanup_worker_reclaims_expired_processing_lease(
    cleanup_session_factory,
):
    event_id = await _enqueue(cleanup_session_factory, file_id="drive-file-expired")
    now = datetime.now(timezone.utc) + timedelta(minutes=1)
    async with cleanup_session_factory() as session:
        event = await session.get(IntegrationOutboxEvent, event_id)
        assert event is not None
        event.status = "processing"
        event.worker_id = "crashed-worker"
        event.lease_token = "expired-token"
        event.lease_expires_at = now - timedelta(seconds=1)
        session.add(event)
        await session.commit()

    google_service = _SuccessfulGoogleService()
    outcome = await OrderDocumentCleanupService.process_next(
        worker_id="recovery-worker",
        session_factory=cleanup_session_factory,
        google_service=google_service,
        now=now,
    )

    assert outcome is not None
    assert outcome.outcome == "deleted"
    assert google_service.deleted_file_ids == ["drive-file-expired"]
