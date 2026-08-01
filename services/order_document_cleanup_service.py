"""Durable, tenant-aware cleanup of Google Drive files after order deletion."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import and_, or_
from sqlmodel import select

from core.database import async_session_maker
from core.logger import logger
from models import IntegrationOutboxEvent
from services.communications.outbox_service import IntegrationOutboxService
from services.google_service import get_google_service
from services.tenant_scope_service import TenantScope


ORDER_DOCUMENT_DELETE_REQUESTED_EVENT = "order.document.delete_requested.v1"


class OrderDocumentDeleteRequestedV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: int = Field(gt=0)
    storefront_id: int = Field(gt=0)
    order_id: int = Field(gt=0)
    document_id: int = Field(gt=0)
    google_file_id: str = Field(min_length=1, max_length=512)


class InvalidOrderDocumentCleanupEvent(ValueError):
    pass


@dataclass(frozen=True)
class DocumentCleanupClaim:
    event_id: str
    lease_token: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


@dataclass(frozen=True)
class DocumentCleanupOutcome:
    event_id: str
    outcome: str
    attempts: int
    next_attempt_at: datetime | None = None


class OrderDocumentCleanupService:
    LEASE_SECONDS = 120
    RETRY_BASE_SECONDS = 30
    RETRY_MAX_SECONDS = 3600

    @staticmethod
    async def enqueue_order_documents(
        session,
        *,
        order_id: int,
        documents: Iterable[Any],
        tenant_scope: TenantScope,
    ) -> int:
        enqueued = 0
        seen_file_ids: set[str] = set()
        for document in documents:
            file_id = str(getattr(document, "google_file_id", "") or "").strip()
            document_id = int(getattr(document, "id", 0) or 0)
            if not file_id or not document_id or file_id in seen_file_ids:
                continue
            seen_file_ids.add(file_id)
            payload = OrderDocumentDeleteRequestedV1(
                tenant_id=tenant_scope.tenant_id,
                storefront_id=tenant_scope.storefront_id,
                order_id=order_id,
                document_id=document_id,
                google_file_id=file_id,
            )
            await IntegrationOutboxService.enqueue(
                session,
                event_type=ORDER_DOCUMENT_DELETE_REQUESTED_EVENT,
                aggregate_type="order_document",
                aggregate_id=document_id,
                aggregate_version=1,
                payload=payload,
                priority=50,
                max_attempts=12,
            )
            enqueued += 1
        return enqueued

    @classmethod
    async def process_next(
        cls,
        *,
        worker_id: str,
        session_factory=async_session_maker,
        google_service=None,
        now: datetime | None = None,
    ) -> DocumentCleanupOutcome | None:
        normalized_worker_id = str(worker_id or "").strip()
        if not normalized_worker_id:
            raise ValueError("Document cleanup worker_id is required")
        if len(normalized_worker_id) > 128:
            raise ValueError("Document cleanup worker_id is too long")

        process_time = now or datetime.now(timezone.utc)
        claim = await cls._claim_next(
            worker_id=normalized_worker_id,
            session_factory=session_factory,
            now=process_time,
        )
        if claim is None:
            return None

        try:
            try:
                payload = OrderDocumentDeleteRequestedV1.model_validate(claim.payload)
            except ValidationError as exc:
                raise InvalidOrderDocumentCleanupEvent(
                    "Document cleanup payload is invalid"
                ) from exc
            service = google_service or get_google_service()
            await asyncio.to_thread(
                service.delete_file_strict,
                payload.google_file_id,
            )
        except Exception as exc:
            permanent = isinstance(exc, InvalidOrderDocumentCleanupEvent)
            return await cls._finish_failure(
                claim=claim,
                error=exc,
                permanent=permanent,
                session_factory=session_factory,
                now=process_time,
            )

        return await cls._finish_success(
            claim=claim,
            session_factory=session_factory,
            now=process_time,
        )

    @classmethod
    async def process_batch(
        cls,
        *,
        worker_id: str,
        limit: int = 25,
        session_factory=async_session_maker,
        google_service=None,
    ) -> list[DocumentCleanupOutcome]:
        outcomes = []
        for _ in range(max(1, min(int(limit), 100))):
            outcome = await cls.process_next(
                worker_id=worker_id,
                session_factory=session_factory,
                google_service=google_service,
            )
            if outcome is None:
                break
            outcomes.append(outcome)
        return outcomes

    @classmethod
    async def _claim_next(
        cls,
        *,
        worker_id: str,
        session_factory,
        now: datetime,
    ) -> DocumentCleanupClaim | None:
        async with session_factory() as session:
            async with session.begin():
                query = (
                    select(IntegrationOutboxEvent)
                    .where(
                        IntegrationOutboxEvent.event_type
                        == ORDER_DOCUMENT_DELETE_REQUESTED_EVENT,
                        or_(
                            and_(
                                IntegrationOutboxEvent.status == "pending",
                                IntegrationOutboxEvent.available_at <= now,
                            ),
                            and_(
                                IntegrationOutboxEvent.status == "processing",
                                IntegrationOutboxEvent.lease_expires_at.is_not(None),
                                IntegrationOutboxEvent.lease_expires_at <= now,
                            ),
                        ),
                    )
                    .order_by(
                        IntegrationOutboxEvent.priority.asc(),
                        IntegrationOutboxEvent.available_at.asc(),
                        IntegrationOutboxEvent.event_id.asc(),
                    )
                    .limit(1)
                )
                if session.get_bind().dialect.name == "postgresql":
                    query = query.with_for_update(skip_locked=True)
                event = (await session.execute(query)).scalar_one_or_none()
                if event is None:
                    return None

                lease_token = uuid.uuid4().hex
                event.status = "processing"
                event.attempts += 1
                event.worker_id = worker_id
                event.lease_token = lease_token
                event.lease_expires_at = now + timedelta(seconds=cls.LEASE_SECONDS)
                event.last_error_code = None
                event.last_error_message = None
                event.updated_at = now
                session.add(event)
                return DocumentCleanupClaim(
                    event_id=event.event_id,
                    lease_token=lease_token,
                    payload=dict(event.payload or {}),
                    attempts=event.attempts,
                    max_attempts=event.max_attempts,
                )

    @classmethod
    async def _finish_success(
        cls,
        *,
        claim: DocumentCleanupClaim,
        session_factory,
        now: datetime,
    ) -> DocumentCleanupOutcome:
        async with session_factory() as session:
            async with session.begin():
                event = await cls._leased_event(
                    session,
                    claim=claim,
                )
                if event is None:
                    return DocumentCleanupOutcome(
                        event_id=claim.event_id,
                        outcome="lease_lost",
                        attempts=claim.attempts,
                    )
                event.status = "published"
                event.published_at = now
                cls._clear_lease(event)
                event.last_error_code = None
                event.last_error_message = None
                event.updated_at = now
                session.add(event)
        return DocumentCleanupOutcome(
            event_id=claim.event_id,
            outcome="deleted",
            attempts=claim.attempts,
        )

    @classmethod
    async def _finish_failure(
        cls,
        *,
        claim: DocumentCleanupClaim,
        error: Exception,
        permanent: bool,
        session_factory,
        now: datetime,
    ) -> DocumentCleanupOutcome:
        is_dead = permanent or claim.attempts >= claim.max_attempts
        next_attempt_at = None
        if not is_dead:
            next_attempt_at = now + cls._retry_delay(
                event_id=claim.event_id,
                attempts=claim.attempts,
            )

        async with session_factory() as session:
            async with session.begin():
                event = await cls._leased_event(
                    session,
                    claim=claim,
                )
                if event is None:
                    return DocumentCleanupOutcome(
                        event_id=claim.event_id,
                        outcome="lease_lost",
                        attempts=claim.attempts,
                    )
                event.status = "dead" if is_dead else "pending"
                if next_attempt_at is not None:
                    event.available_at = next_attempt_at
                cls._clear_lease(event)
                event.last_error_code = type(error).__name__[:100]
                event.last_error_message = (
                    str(error).strip() or type(error).__name__
                )[:1000]
                event.updated_at = now
                session.add(event)

        logger.warning(
            "Order document cleanup failed event_id=%s outcome=%s attempts=%s error_code=%s",
            claim.event_id,
            "dead" if is_dead else "retry_scheduled",
            claim.attempts,
            type(error).__name__,
        )
        return DocumentCleanupOutcome(
            event_id=claim.event_id,
            outcome="dead" if is_dead else "retry_scheduled",
            attempts=claim.attempts,
            next_attempt_at=next_attempt_at,
        )

    @staticmethod
    async def _leased_event(
        session,
        *,
        claim: DocumentCleanupClaim,
    ) -> IntegrationOutboxEvent | None:
        query = select(IntegrationOutboxEvent).where(
            IntegrationOutboxEvent.event_id == claim.event_id,
            IntegrationOutboxEvent.status == "processing",
            IntegrationOutboxEvent.lease_token == claim.lease_token,
        )
        if session.get_bind().dialect.name == "postgresql":
            query = query.with_for_update()
        return (await session.execute(query)).scalar_one_or_none()

    @staticmethod
    def _clear_lease(event: IntegrationOutboxEvent) -> None:
        event.worker_id = None
        event.lease_token = None
        event.lease_expires_at = None

    @classmethod
    def _retry_delay(cls, *, event_id: str, attempts: int) -> timedelta:
        exponent = max(0, min(int(attempts) - 1, 16))
        base_seconds = min(
            cls.RETRY_MAX_SECONDS,
            cls.RETRY_BASE_SECONDS * (2**exponent),
        )
        jitter_window = max(1, base_seconds // 5)
        digest = hashlib.sha256(f"{event_id}:{attempts}".encode()).digest()
        jitter_seconds = int.from_bytes(digest[:4], "big") % (jitter_window + 1)
        return timedelta(
            seconds=min(cls.RETRY_MAX_SECONDS, base_seconds + jitter_seconds)
        )
