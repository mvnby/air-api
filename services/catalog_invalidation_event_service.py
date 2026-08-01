from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from crud.catalog_invalidation import CatalogInvalidationEventDAO
from models import IntegrationOutboxEvent
from services.catalog_invalidation_contracts import (
    CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
    CATALOG_INVALIDATION_SCHEMA_VERSION,
    CatalogCacheInvalidationRequestedV1,
)
from services.communications.outbox_service import IntegrationOutboxService


class CatalogInvalidationLeaseLost(RuntimeError):
    pass


@dataclass(frozen=True)
class CatalogInvalidationClaim:
    event_id: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    worker_id: str
    lease_token: str
    lease_expires_at: datetime


@dataclass(frozen=True)
class CatalogInvalidationRecovery:
    retry_count: int = 0
    dead_count: int = 0


@dataclass(frozen=True)
class CatalogInvalidationTransition:
    outcome: Literal["published", "retry", "dead"]
    attempts: int
    next_attempt_at: datetime | None = None


class CatalogInvalidationEventService:
    RETRY_BASE_SECONDS = 30
    RETRY_MAX_SECONDS = 3600
    MAX_RECOVERY_LIMIT = 1000

    @classmethod
    async def enqueue_requested(
        cls,
        session: AsyncSession,
        *,
        payload: CatalogCacheInvalidationRequestedV1,
        idempotency_key: str,
        priority: int = 40,
        max_attempts: int = 12,
    ) -> IntegrationOutboxEvent:
        """Enqueue one exact event using the database clock.

        The caller owns the surrounding business transaction. Updating all
        scheduling timestamps after the conflict-safe insert keeps claim order
        independent from application-host clock drift.
        """

        authoritative_now = await CatalogInvalidationEventDAO.database_now(
            session
        )
        result = await IntegrationOutboxService.enqueue_with_result(
            session,
            event_type=CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
            schema_version=CATALOG_INVALIDATION_SCHEMA_VERSION,
            aggregate_type="storefront_catalog",
            aggregate_id=f"{payload.tenant_id}:{payload.storefront_id}",
            idempotency_key=idempotency_key,
            payload=payload,
            occurred_at=authoritative_now,
            priority=priority,
            max_attempts=max_attempts,
        )
        if result.created:
            result.event.occurred_at = authoritative_now
            result.event.available_at = authoritative_now
            result.event.created_at = authoritative_now
            result.event.updated_at = authoritative_now
            session.add(result.event)
            await session.flush()
        return result.event

    @classmethod
    async def claim_next(
        cls,
        session: AsyncSession,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> CatalogInvalidationClaim | None:
        normalized_worker_id = cls._normalize_worker_id(worker_id)
        normalized_lease_seconds = cls._normalize_lease_seconds(lease_seconds)
        now = await CatalogInvalidationEventDAO.database_now(session)
        event = await CatalogInvalidationEventDAO.claimable_event(
            session,
            now=now,
        )
        if event is None:
            return None

        event.status = "processing"
        event.attempts = int(event.attempts) + 1
        event.worker_id = normalized_worker_id
        event.lease_token = secrets.token_urlsafe(32)
        event.lease_expires_at = now + timedelta(
            seconds=normalized_lease_seconds
        )
        event.last_error_code = None
        event.last_error_message = None
        event.updated_at = now
        session.add(event)
        await session.flush()
        return CatalogInvalidationClaim(
            event_id=event.event_id,
            payload=dict(event.payload or {}),
            attempts=event.attempts,
            max_attempts=event.max_attempts,
            worker_id=normalized_worker_id,
            lease_token=event.lease_token,
            lease_expires_at=event.lease_expires_at,
        )

    @classmethod
    async def renew(
        cls,
        session: AsyncSession,
        *,
        claim: CatalogInvalidationClaim,
        lease_seconds: int,
    ) -> datetime:
        now = await CatalogInvalidationEventDAO.database_now(session)
        event = await cls._owned_event(session, claim=claim, now=now)
        event.lease_expires_at = now + timedelta(
            seconds=cls._normalize_lease_seconds(lease_seconds)
        )
        event.updated_at = now
        session.add(event)
        await session.flush()
        return event.lease_expires_at

    @classmethod
    async def acknowledge(
        cls,
        session: AsyncSession,
        *,
        claim: CatalogInvalidationClaim,
    ) -> CatalogInvalidationTransition:
        now = await CatalogInvalidationEventDAO.database_now(session)
        event = await cls._owned_event(session, claim=claim, now=now)
        event.status = "published"
        event.published_at = now
        cls._clear_lease(event)
        event.last_error_code = None
        event.last_error_message = None
        event.updated_at = now
        session.add(event)
        await session.flush()
        return CatalogInvalidationTransition(
            outcome="published",
            attempts=event.attempts,
        )

    @classmethod
    async def fail(
        cls,
        session: AsyncSession,
        *,
        claim: CatalogInvalidationClaim,
        error: BaseException,
        permanent: bool = False,
    ) -> CatalogInvalidationTransition:
        now = await CatalogInvalidationEventDAO.database_now(session)
        event = await cls._owned_event(session, claim=claim, now=now)
        is_dead = permanent or event.attempts >= event.max_attempts
        next_attempt_at = None
        if is_dead:
            event.status = "dead"
        else:
            event.status = "pending"
            next_attempt_at = now + cls.retry_delay(
                event_id=event.event_id,
                attempts=event.attempts,
            )
            event.available_at = next_attempt_at
        cls._clear_lease(event)
        event.last_error_code = cls._safe_error_code(error)
        event.last_error_message = cls._safe_error_message(error)
        event.updated_at = now
        session.add(event)
        await session.flush()
        return CatalogInvalidationTransition(
            outcome="dead" if is_dead else "retry",
            attempts=event.attempts,
            next_attempt_at=next_attempt_at,
        )

    @classmethod
    async def recover_expired(
        cls,
        session: AsyncSession,
        *,
        limit: int,
    ) -> CatalogInvalidationRecovery:
        now = await CatalogInvalidationEventDAO.database_now(session)
        safe_limit = max(1, min(cls.MAX_RECOVERY_LIMIT, int(limit)))
        events = await CatalogInvalidationEventDAO.expired_events(
            session,
            now=now,
            limit=safe_limit,
        )
        retry_count = 0
        dead_count = 0
        for event in events:
            if event.attempts >= event.max_attempts:
                event.status = "dead"
                dead_count += 1
            else:
                event.status = "pending"
                event.available_at = now + cls.retry_delay(
                    event_id=event.event_id,
                    attempts=event.attempts,
                )
                retry_count += 1
            cls._clear_lease(event)
            event.last_error_code = "catalog_invalidation_lease_expired"
            event.last_error_message = "Catalog invalidation lease expired"
            event.updated_at = now
            session.add(event)
        await session.flush()
        return CatalogInvalidationRecovery(
            retry_count=retry_count,
            dead_count=dead_count,
        )

    @classmethod
    async def _owned_event(
        cls,
        session: AsyncSession,
        *,
        claim: CatalogInvalidationClaim,
        now: datetime,
    ):
        event = await CatalogInvalidationEventDAO.owned_event(
            session,
            event_id=claim.event_id,
            worker_id=claim.worker_id,
            lease_token=claim.lease_token,
            now=now,
        )
        if event is None:
            raise CatalogInvalidationLeaseLost(
                "Catalog invalidation lease is no longer owned"
            )
        return event

    @staticmethod
    def _clear_lease(event) -> None:
        event.worker_id = None
        event.lease_token = None
        event.lease_expires_at = None

    @classmethod
    def retry_delay(cls, *, event_id: str, attempts: int) -> timedelta:
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

    @staticmethod
    def _normalize_worker_id(worker_id: str) -> str:
        normalized = str(worker_id or "").strip()
        if not normalized or len(normalized) > 128:
            raise ValueError("Catalog invalidation worker_id is invalid")
        return normalized

    @staticmethod
    def _normalize_lease_seconds(lease_seconds: int) -> int:
        normalized = int(lease_seconds)
        if normalized < 30 or normalized > 3600:
            raise ValueError(
                "Catalog invalidation lease_seconds must be between 30 and 3600"
            )
        return normalized

    @staticmethod
    def _safe_error_code(error: BaseException) -> str:
        normalized = "".join(
            character if character.isalnum() or character == "_" else "_"
            for character in type(error).__name__
        )
        return (normalized or "CatalogInvalidationError")[:100]

    @staticmethod
    def _safe_error_message(error: BaseException) -> str:
        # Provider responses can contain operational identifiers or reflected
        # request details. Persist only a stable, non-sensitive classification.
        return f"Catalog invalidation failed: {type(error).__name__}"[:1000]
