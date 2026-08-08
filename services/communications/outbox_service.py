from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import IntegrationOutboxEvent
from services.communications.contracts import IntegrationEventEnvelopeV1
from services.communications.installation_activation_fence import (
    acquire_website_communication_enqueue_fence,
)
from services.communications.tenant_website_events import (
    TENANT_WEBSITE_EVENT_TYPES,
)


class OutboxEventConflictError(ValueError):
    """The same deterministic event key was reused with different content."""


@dataclass(frozen=True)
class IntegrationOutboxEnqueueResult:
    event: IntegrationOutboxEvent
    created: bool


class IntegrationOutboxService:
    _EVENT_NAMESPACE = uuid.UUID("970f0f76-e63c-4ea3-bb82-e955470f5af9")

    @staticmethod
    def build_deduplication_key(
        *,
        event_type: str,
        schema_version: int,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_version: int | None,
        idempotency_key: str | None,
    ) -> str:
        if aggregate_version is None and not idempotency_key:
            raise ValueError(
                "Outbox events require aggregate_version or idempotency_key"
            )
        identity = [
            event_type,
            schema_version,
            aggregate_type,
            aggregate_id,
            aggregate_version,
            idempotency_key,
        ]
        canonical_identity = json.dumps(
            identity,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical_identity.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    @classmethod
    def build_event_id(cls, deduplication_key: str) -> str:
        return uuid.uuid5(cls._EVENT_NAMESPACE, deduplication_key).hex

    @staticmethod
    def _normalize_payload(payload: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
        normalized = (
            payload.model_dump(mode="json")
            if isinstance(payload, BaseModel)
            else dict(payload)
        )
        try:
            serialized = json.dumps(
                normalized,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Outbox payload must be JSON serializable") from exc
        return json.loads(serialized)

    @staticmethod
    async def _find_existing(
        session: AsyncSession,
        *,
        event_id: str,
        deduplication_key: str,
    ) -> IntegrationOutboxEvent | None:
        result = await session.execute(
            select(IntegrationOutboxEvent).where(
                or_(
                    IntegrationOutboxEvent.event_id == event_id,
                    IntegrationOutboxEvent.deduplication_key == deduplication_key,
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _ensure_same_event(
        existing: IntegrationOutboxEvent,
        envelope: IntegrationEventEnvelopeV1,
        deduplication_key: str,
    ) -> None:
        existing_identity = (
            existing.event_id,
            existing.deduplication_key,
            existing.event_type,
            existing.schema_version,
            existing.aggregate_type,
            existing.aggregate_id,
            existing.aggregate_version,
            existing.idempotency_key,
            existing.payload,
        )
        requested_identity = (
            envelope.event_id,
            deduplication_key,
            envelope.event_type,
            envelope.schema_version,
            envelope.aggregate_type,
            envelope.aggregate_id,
            envelope.aggregate_version,
            envelope.idempotency_key,
            envelope.payload,
        )
        if existing_identity != requested_identity:
            raise OutboxEventConflictError(
                "Outbox deduplication key was reused with different event content"
            )

    @classmethod
    async def enqueue_with_result(
        cls,
        session: AsyncSession,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: int | str,
        payload: BaseModel | Mapping[str, Any],
        schema_version: int = 1,
        aggregate_version: int | None = None,
        occurred_at: datetime | None = None,
        actor_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        idempotency_key: str | None = None,
        priority: int = 100,
        max_attempts: int = 8,
    ) -> IntegrationOutboxEnqueueResult:
        """Add an event and report whether this transaction inserted it."""

        normalized_payload = cls._normalize_payload(payload)
        normalized_event_type = str(event_type).strip()
        authoritative_created_at: datetime | None = None
        if normalized_event_type in TENANT_WEBSITE_EVENT_TYPES:
            # Acquire before constructing the model: its ``created_at`` default
            # must be a DB timestamp ordered after any committed activation
            # watermark that won the exclusive side of this fence.
            authoritative_created_at = (
                await acquire_website_communication_enqueue_fence(session)
            )
        normalized_aggregate_type = str(aggregate_type).strip()
        normalized_aggregate_id = str(aggregate_id).strip()
        normalized_idempotency_key = (
            str(idempotency_key).strip() or None
            if idempotency_key is not None
            else None
        )
        deduplication_key = cls.build_deduplication_key(
            event_type=normalized_event_type,
            schema_version=schema_version,
            aggregate_type=normalized_aggregate_type,
            aggregate_id=normalized_aggregate_id,
            aggregate_version=aggregate_version,
            idempotency_key=normalized_idempotency_key,
        )
        event_id = cls.build_event_id(deduplication_key)
        normalized_occurred_at = (
            occurred_at
            or authoritative_created_at
            or datetime.now(timezone.utc)
        )
        envelope = IntegrationEventEnvelopeV1(
            event_id=event_id,
            event_type=normalized_event_type,
            schema_version=schema_version,
            aggregate_type=normalized_aggregate_type,
            aggregate_id=normalized_aggregate_id,
            aggregate_version=aggregate_version,
            occurred_at=normalized_occurred_at,
            actor_id=actor_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            idempotency_key=normalized_idempotency_key,
            payload=normalized_payload,
        )

        existing = await cls._find_existing(
            session,
            event_id=event_id,
            deduplication_key=deduplication_key,
        )
        if existing is not None:
            cls._ensure_same_event(existing, envelope, deduplication_key)
            return IntegrationOutboxEnqueueResult(event=existing, created=False)

        event = IntegrationOutboxEvent(
            event_id=envelope.event_id,
            event_type=envelope.event_type,
            schema_version=envelope.schema_version,
            aggregate_type=envelope.aggregate_type,
            aggregate_id=envelope.aggregate_id,
            aggregate_version=envelope.aggregate_version,
            deduplication_key=deduplication_key,
            idempotency_key=envelope.idempotency_key,
            actor_id=envelope.actor_id,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.causation_id,
            payload=envelope.payload,
            priority=max(0, int(priority)),
            max_attempts=max(1, int(max_attempts)),
            occurred_at=envelope.occurred_at,
            available_at=envelope.occurred_at,
            **(
                {
                    "created_at": authoritative_created_at,
                    "updated_at": authoritative_created_at,
                }
                if authoritative_created_at is not None
                else {}
            ),
        )
        dialect_name = session.get_bind().dialect.name
        event_values = event.model_dump()
        if dialect_name == "postgresql":
            statement = postgresql_insert(IntegrationOutboxEvent).values(**event_values)
        elif dialect_name == "sqlite":
            statement = sqlite_insert(IntegrationOutboxEvent).values(**event_values)
        else:
            raise NotImplementedError(
                f"Atomic outbox enqueue is not implemented for dialect {dialect_name!r}"
            )

        inserted_event_id = (
            await session.execute(
                statement.on_conflict_do_nothing(
                    index_elements=[IntegrationOutboxEvent.deduplication_key]
                ).returning(IntegrationOutboxEvent.event_id)
            )
        ).scalar_one_or_none()
        existing = await cls._find_existing(
            session,
            event_id=inserted_event_id or event_id,
            deduplication_key=deduplication_key,
        )
        if existing is None:
            raise RuntimeError("Outbox event insert completed without a readable row")
        cls._ensure_same_event(existing, envelope, deduplication_key)
        return IntegrationOutboxEnqueueResult(
            event=existing,
            created=inserted_event_id is not None,
        )

    @classmethod
    async def enqueue(
        cls,
        session: AsyncSession,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: int | str,
        payload: BaseModel | Mapping[str, Any],
        schema_version: int = 1,
        aggregate_version: int | None = None,
        occurred_at: datetime | None = None,
        actor_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        idempotency_key: str | None = None,
        priority: int = 100,
        max_attempts: int = 8,
    ) -> IntegrationOutboxEvent:
        """Add an event to the caller-owned transaction without committing it."""

        result = await cls.enqueue_with_result(
            session,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            schema_version=schema_version,
            aggregate_version=aggregate_version,
            occurred_at=occurred_at,
            actor_id=actor_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            idempotency_key=idempotency_key,
            priority=priority,
            max_attempts=max_attempts,
        )
        return result.event
