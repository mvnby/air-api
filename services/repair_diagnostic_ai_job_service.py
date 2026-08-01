from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.database import async_session_maker
from models import IntegrationOutboxEvent
from services.communications.outbox_service import IntegrationOutboxService
from services.tenant_scope_service import TenantScope


REPAIR_DIAGNOSTIC_AI_REQUESTED_EVENT = "repair.diagnostic_ai_requested.v1"


@dataclass(frozen=True)
class RepairDiagnosticAiJobClaim:
    event_id: str
    lease_token: str
    order_id: int
    tenant_id: int


class RepairDiagnosticAiJobService:
    LEASE_SECONDS = 5 * 60

    @staticmethod
    async def enqueue(
        session: AsyncSession,
        *,
        order_id: int,
        tenant_scope: TenantScope,
        key_hash: str,
    ) -> IntegrationOutboxEvent:
        return await IntegrationOutboxService.enqueue(
            session,
            event_type=REPAIR_DIAGNOSTIC_AI_REQUESTED_EVENT,
            aggregate_type="order",
            aggregate_id=order_id,
            payload={
                "order_id": order_id,
                "tenant_id": tenant_scope.tenant_id,
                "storefront_id": tenant_scope.storefront_id,
            },
            idempotency_key=f"repair-diagnostic-ai:{key_hash}",
            priority=30,
            max_attempts=8,
        )

    @classmethod
    async def _claim_next(
        cls,
        session: AsyncSession,
        *,
        worker_id: str,
        now: datetime,
    ) -> RepairDiagnosticAiJobClaim | None:
        statement = (
            select(IntegrationOutboxEvent)
            .where(
                IntegrationOutboxEvent.event_type
                == REPAIR_DIAGNOSTIC_AI_REQUESTED_EVENT,
                IntegrationOutboxEvent.available_at <= now,
                or_(
                    IntegrationOutboxEvent.status == "pending",
                    (
                        (IntegrationOutboxEvent.status == "processing")
                        & (IntegrationOutboxEvent.lease_expires_at.is_not(None))
                        & (IntegrationOutboxEvent.lease_expires_at <= now)
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
            statement = statement.with_for_update(skip_locked=True)
        event = await session.scalar(statement)
        if event is None:
            return None
        payload = event.payload if isinstance(event.payload, dict) else {}
        lease_token = secrets.token_hex(16)
        event.status = "processing"
        event.worker_id = worker_id[:128]
        event.lease_token = lease_token
        event.lease_expires_at = now + timedelta(seconds=cls.LEASE_SECONDS)
        event.attempts += 1
        event.updated_at = now
        session.add(event)
        await session.flush()
        return RepairDiagnosticAiJobClaim(
            event_id=event.event_id,
            lease_token=lease_token,
            order_id=int(payload["order_id"]),
            tenant_id=int(payload["tenant_id"]),
        )

    @staticmethod
    async def _finish(
        session: AsyncSession,
        *,
        claim: RepairDiagnosticAiJobClaim,
        error: Exception | None,
        now: datetime,
    ) -> None:
        event = await session.scalar(
            select(IntegrationOutboxEvent).where(
                IntegrationOutboxEvent.event_id == claim.event_id,
                IntegrationOutboxEvent.status == "processing",
                IntegrationOutboxEvent.lease_token == claim.lease_token,
            )
        )
        if event is None:
            return
        event.worker_id = None
        event.lease_token = None
        event.lease_expires_at = None
        event.updated_at = now
        if error is None:
            event.status = "published"
            event.published_at = now
            event.last_error_code = None
            event.last_error_message = None
        else:
            event.last_error_code = type(error).__name__[:100]
            event.last_error_message = str(error)[:1000]
            if event.attempts >= event.max_attempts:
                event.status = "dead"
            else:
                event.status = "pending"
                delay_seconds = min(15 * (2 ** max(0, event.attempts - 1)), 3600)
                event.available_at = now + timedelta(seconds=delay_seconds)
        session.add(event)

    @classmethod
    async def process_batch(
        cls,
        *,
        worker_id: str,
        limit: int = 10,
        session_factory=None,
        runner: Callable[..., Awaitable[None]] | None = None,
    ) -> int:
        from services.repair_diagnostic_service import RepairDiagnosticService

        selected_session_factory = session_factory or async_session_maker
        selected_runner = runner or RepairDiagnosticService.run_ai_pre_diagnosis
        processed = 0
        for _ in range(max(1, min(int(limit), 100))):
            now = datetime.now(timezone.utc)
            async with selected_session_factory() as session:
                async with session.begin():
                    claim = await cls._claim_next(
                        session,
                        worker_id=worker_id,
                        now=now,
                    )
            if claim is None:
                break
            error: Exception | None = None
            try:
                await selected_runner(
                    order_id=claim.order_id,
                    tenant_id=claim.tenant_id,
                )
            except Exception as exc:  # pragma: no cover - runtime retry guard
                error = exc
            async with selected_session_factory() as session:
                async with session.begin():
                    await cls._finish(
                        session,
                        claim=claim,
                        error=error,
                        now=datetime.now(timezone.utc),
                    )
            processed += 1
        return processed
