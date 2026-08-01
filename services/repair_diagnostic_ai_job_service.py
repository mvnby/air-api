from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.database import async_session_maker
from models import IntegrationOutboxEvent
from services.communications.outbox_service import IntegrationOutboxService
from services.repair_diagnostic_ai_service import (
    RepairDiagnosticAiLeaseLost,
    RepairDiagnosticAiRetryableError,
    RepairDiagnosticAiService,
)
from services.tenant_scope_service import TenantScope


REPAIR_DIAGNOSTIC_AI_REQUESTED_EVENT = "repair.diagnostic_ai_requested.v1"


@dataclass(frozen=True)
class RepairDiagnosticAiJobClaim:
    event_id: str
    lease_token: str
    worker_id: str
    order_id: int
    tenant_id: int
    attempts: int
    max_attempts: int


class RepairDiagnosticAiJobService:
    LEASE_SECONDS = 5 * 60
    RETRY_MAX_SECONDS = 60 * 60

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
                IntegrationOutboxEvent.attempts
                < IntegrationOutboxEvent.max_attempts,
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
            statement = statement.with_for_update(skip_locked=True)
        event = await session.scalar(statement)
        if event is None:
            return None
        payload = event.payload if isinstance(event.payload, dict) else {}
        lease_token = secrets.token_hex(16)
        normalized_worker_id = str(worker_id)[:128]
        event.status = "processing"
        event.worker_id = normalized_worker_id
        event.lease_token = lease_token
        event.lease_expires_at = now + timedelta(seconds=cls.LEASE_SECONDS)
        event.attempts += 1
        event.updated_at = now
        session.add(event)
        await session.flush()
        return RepairDiagnosticAiJobClaim(
            event_id=event.event_id,
            lease_token=lease_token,
            worker_id=normalized_worker_id,
            order_id=int(payload["order_id"]),
            tenant_id=int(payload["tenant_id"]),
            attempts=int(event.attempts),
            max_attempts=int(event.max_attempts),
        )

    @classmethod
    async def _renew_lease(
        cls,
        session: AsyncSession,
        *,
        claim: RepairDiagnosticAiJobClaim,
        now: datetime,
    ) -> bool:
        statement = select(IntegrationOutboxEvent).where(
            IntegrationOutboxEvent.event_id == claim.event_id,
            IntegrationOutboxEvent.status == "processing",
            IntegrationOutboxEvent.worker_id == claim.worker_id,
            IntegrationOutboxEvent.lease_token == claim.lease_token,
            IntegrationOutboxEvent.lease_expires_at.is_not(None),
            IntegrationOutboxEvent.lease_expires_at > now,
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update()
        event = await session.scalar(statement)
        if event is None:
            return False
        event.lease_expires_at = now + timedelta(seconds=cls.LEASE_SECONDS)
        event.updated_at = now
        session.add(event)
        await session.flush()
        return True

    @classmethod
    async def _heartbeat_loop(
        cls,
        *,
        claim: RepairDiagnosticAiJobClaim,
        session_factory,
        stop: asyncio.Event,
    ) -> bool:
        interval = max(0.05, min(60.0, float(cls.LEASE_SECONDS) / 3.0))
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                return True
            except TimeoutError:
                pass
            try:
                async with session_factory() as session:
                    async with session.begin():
                        renewed = await cls._renew_lease(
                            session,
                            claim=claim,
                            now=datetime.now(timezone.utc),
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                return False
            if not renewed:
                return False

    @classmethod
    async def _execute_claim(
        cls,
        *,
        claim: RepairDiagnosticAiJobClaim,
        session_factory,
        runner: Callable[..., Awaitable[None]],
        production_runner: bool,
    ) -> Exception | None:
        stop = asyncio.Event()

        async def invoke_runner() -> None:
            kwargs = {
                "order_id": claim.order_id,
                "tenant_id": claim.tenant_id,
            }
            if production_runner:
                kwargs.update(
                    {
                        "job_event_id": claim.event_id,
                        "job_lease_token": claim.lease_token,
                    }
                )
            await runner(**kwargs)

        runner_task = asyncio.create_task(invoke_runner())
        heartbeat_task = asyncio.create_task(
            cls._heartbeat_loop(
                claim=claim,
                session_factory=session_factory,
                stop=stop,
            )
        )
        error: Exception | None = None
        try:
            done, _ = await asyncio.wait(
                {runner_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done and not runner_task.done():
                heartbeat_ok = heartbeat_task.result()
                if not heartbeat_ok:
                    error = RepairDiagnosticAiRetryableError(
                        "repair_ai_lease_heartbeat_failed",
                        "Repair diagnostic AI lease heartbeat failed",
                    )
                    runner_task.cancel()
            if error is None:
                try:
                    await runner_task
                except Exception as exc:
                    error = exc
        except asyncio.CancelledError:
            runner_task.cancel()
            heartbeat_task.cancel()
            await asyncio.gather(
                runner_task,
                heartbeat_task,
                return_exceptions=True,
            )
            raise
        finally:
            stop.set()
            if not heartbeat_task.done():
                try:
                    await asyncio.shield(heartbeat_task)
                except asyncio.CancelledError:
                    heartbeat_task.cancel()
                    await asyncio.gather(
                        heartbeat_task,
                        return_exceptions=True,
                    )
                    raise
            await asyncio.gather(runner_task, return_exceptions=True)

        if heartbeat_task.cancelled():
            return error or RepairDiagnosticAiLeaseLost()
        try:
            heartbeat_ok = heartbeat_task.result()
        except Exception:
            heartbeat_ok = False
        if not heartbeat_ok and error is None:
            return RepairDiagnosticAiRetryableError(
                "repair_ai_lease_heartbeat_failed",
                "Repair diagnostic AI lease heartbeat failed",
            )
        return error

    @classmethod
    async def _finish(
        cls,
        session: AsyncSession,
        *,
        claim: RepairDiagnosticAiJobClaim,
        error: Exception | None,
        now: datetime,
    ) -> str:
        statement = select(IntegrationOutboxEvent).where(
            IntegrationOutboxEvent.event_id == claim.event_id,
            IntegrationOutboxEvent.status == "processing",
            IntegrationOutboxEvent.worker_id == claim.worker_id,
            IntegrationOutboxEvent.lease_token == claim.lease_token,
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update()
        event = await session.scalar(statement)
        if event is None:
            return "lease_lost"

        event.worker_id = None
        event.lease_token = None
        event.lease_expires_at = None
        event.updated_at = now
        if error is None:
            event.status = "published"
            event.published_at = now
            event.last_error_code = None
            event.last_error_message = None
            outcome = "published"
        else:
            error_code = str(
                getattr(error, "code", type(error).__name__)
            )[:100]
            event.last_error_code = error_code
            event.last_error_message = "Repair diagnostic AI attempt failed"
            event.published_at = None
            if claim.attempts >= claim.max_attempts:
                event.status = "dead"
                await RepairDiagnosticAiService.mark_exhausted_failure(
                    session,
                    order_id=claim.order_id,
                    tenant_id=claim.tenant_id,
                    error_code=error_code,
                )
                outcome = "dead"
            else:
                event.status = "pending"
                event.available_at = now + cls._retry_delay(claim.attempts)
                outcome = "retry_scheduled"
        session.add(event)
        return outcome

    @classmethod
    async def _recover_exhausted(
        cls,
        session: AsyncSession,
        *,
        now: datetime,
    ) -> bool:
        statement = (
            select(IntegrationOutboxEvent)
            .where(
                IntegrationOutboxEvent.event_type
                == REPAIR_DIAGNOSTIC_AI_REQUESTED_EVENT,
                IntegrationOutboxEvent.attempts
                >= IntegrationOutboxEvent.max_attempts,
                or_(
                    and_(
                        IntegrationOutboxEvent.status == "processing",
                        IntegrationOutboxEvent.lease_expires_at.is_not(None),
                        IntegrationOutboxEvent.lease_expires_at <= now,
                    ),
                    and_(
                        IntegrationOutboxEvent.status == "pending",
                        IntegrationOutboxEvent.available_at <= now,
                    ),
                ),
            )
            .order_by(IntegrationOutboxEvent.event_id.asc())
            .limit(1)
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        event = await session.scalar(statement)
        if event is None:
            return False
        payload = event.payload if isinstance(event.payload, dict) else {}
        event.status = "dead"
        event.worker_id = None
        event.lease_token = None
        event.lease_expires_at = None
        event.last_error_code = "repair_ai_lease_expired_after_exhaustion"
        event.last_error_message = "Repair diagnostic AI attempt failed"
        event.updated_at = now
        await RepairDiagnosticAiService.mark_exhausted_failure(
            session,
            order_id=int(payload["order_id"]),
            tenant_id=int(payload["tenant_id"]),
            error_code=event.last_error_code,
        )
        session.add(event)
        return True

    @classmethod
    async def process_batch(
        cls,
        *,
        worker_id: str,
        limit: int = 10,
        session_factory=None,
        runner: Callable[..., Awaitable[None]] | None = None,
    ) -> int:
        selected_session_factory = session_factory or async_session_maker
        selected_runner = runner or RepairDiagnosticAiService.run
        production_runner = runner is None
        processed = 0
        for _ in range(max(1, min(int(limit), 100))):
            now = datetime.now(timezone.utc)
            async with selected_session_factory() as session:
                async with session.begin():
                    recovered = await cls._recover_exhausted(
                        session,
                        now=now,
                    )
                    claim = None
                    if not recovered:
                        claim = await cls._claim_next(
                            session,
                            worker_id=worker_id,
                            now=now,
                        )
            if recovered:
                processed += 1
                continue
            if claim is None:
                break

            error = await cls._execute_claim(
                claim=claim,
                session_factory=selected_session_factory,
                runner=selected_runner,
                production_runner=production_runner,
            )
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

    @classmethod
    def _retry_delay(cls, attempts: int) -> timedelta:
        delay_seconds = min(
            15 * (2 ** max(0, int(attempts) - 1)),
            cls.RETRY_MAX_SECONDS,
        )
        return timedelta(seconds=delay_seconds)
