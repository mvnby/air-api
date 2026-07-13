from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from services.communications.contracts import CommunicationTemplatePlanV1
from services.communications.delivery_service import (
    ClaimedCommunicationDelivery,
    CommunicationDeliveryLeaseLost,
    CommunicationDeliveryService,
    DeliveryFailureOutcome,
    ExpiredLeaseRecoveryResult,
)
from services.communications.providers.base import (
    CommunicationDeliveryProvider,
    ProviderDeliveryDisposition,
    ProviderDeliveryResult,
)
from services.communications.recipient_directory import ManagementRecipientDirectory
from services.communications.template_registry import WebsiteTemplateRegistry


logger = logging.getLogger(__name__)
_TerminalResult = TypeVar("_TerminalResult")


class _ProviderResultDuringCancellation(RuntimeError):
    def __init__(
        self,
        *,
        result: ProviderDeliveryResult,
        cancellation: asyncio.CancelledError,
    ) -> None:
        super().__init__("Provider result completed during worker cancellation")
        self.result = result
        self.cancellation = cancellation


@dataclass(frozen=True)
class DeliveryRunOutcome:
    outcome: Literal[
        "idle",
        "sent",
        "retry",
        "dead",
        "canceled",
        "lease_lost",
    ]
    delivery_id: str | None = None
    attempts: int | None = None
    next_attempt_at: datetime | None = None
    recovered_retry_count: int = 0
    recovered_dead_count: int = 0


class CommunicationDeliveryWorker:
    """One dormant provider-worker iteration with durable per-recipient leases.

    The caller owns scheduling and provider lifecycle. This module deliberately
    has no runtime imports, feature switches, or producer-side integration.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        provider: CommunicationDeliveryProvider,
        worker_id: str,
        lease_seconds: int = 90,
        recovery_limit: int = 100,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._worker_id = CommunicationDeliveryService._normalize_worker_id(worker_id)
        self._channel = CommunicationDeliveryService._normalize_channel(provider.channel)
        self._lease_seconds = CommunicationDeliveryService._normalize_lease_seconds(
            lease_seconds
        )
        self._recovery_limit = max(
            1,
            min(CommunicationDeliveryService.MAX_RECOVERY_LIMIT, int(recovery_limit)),
        )

    async def run_once(self) -> DeliveryRunOutcome:
        recovery = await self._recover_expired_leases()
        claim = await self._claim_and_commit()
        if claim is None:
            return DeliveryRunOutcome(
                outcome="idle",
                recovered_retry_count=recovery.retry_count,
                recovered_dead_count=recovery.dead_count,
            )

        if not await self._recipient_is_current(claim):
            try:
                await self._finish_terminal_despite_cancellation(
                    self._cancel_inactive_recipient(claim),
                    delivery_id=claim.delivery_id,
                )
            except CommunicationDeliveryLeaseLost:
                return self._lease_lost_outcome(claim, recovery)
            return DeliveryRunOutcome(
                outcome="canceled",
                delivery_id=claim.delivery_id,
                attempts=claim.attempts,
                recovered_retry_count=recovery.retry_count,
                recovered_dead_count=recovery.dead_count,
            )

        try:
            rendered_text = self._render(claim)
        except Exception as exc:
            logger.warning(
                "Communication delivery render failed delivery_id=%s error_type=%s",
                claim.delivery_id,
                type(exc).__name__,
            )
            result = ProviderDeliveryResult.permanent_failure(
                category="template",
                code="template_render_failed",
                message="Communication template could not be rendered",
            )
            return await self._finish_terminal_despite_cancellation(
                self._record_failure(claim, result, recovery),
                delivery_id=claim.delivery_id,
            )

        try:
            await self._renew_before_send(claim)
        except CommunicationDeliveryLeaseLost:
            # Rendering and recipient resolution are deliberately outside the
            # claim transaction. Re-fence immediately before any network I/O.
            return self._lease_lost_outcome(claim, recovery)

        cancellation_after_finalize: asyncio.CancelledError | None = None
        try:
            result = await self._send_with_heartbeat(claim, rendered_text)
        except _ProviderResultDuringCancellation as exc:
            result = exc.result
            cancellation_after_finalize = exc.cancellation
        except CommunicationDeliveryLeaseLost:
            return self._lease_lost_outcome(claim, recovery)
        except asyncio.CancelledError:
            # The durable running row is intentionally left for lease recovery.
            raise
        except Exception as exc:
            logger.warning(
                "Communication provider call failed delivery_id=%s error_type=%s",
                claim.delivery_id,
                type(exc).__name__,
            )
            result = ProviderDeliveryResult.transient_failure(
                category="provider",
                code="provider_call_failed",
                message="Communication provider failed unexpectedly",
            )

        if result.disposition == ProviderDeliveryDisposition.SENT:
            if not result.provider_message_id:
                result = ProviderDeliveryResult.permanent_failure(
                    category="provider",
                    code="provider_result_invalid",
                    message="Communication provider returned an invalid success result",
                )
            else:
                try:
                    await self._finish_terminal_despite_cancellation(
                        self._mark_sent(claim, result.provider_message_id),
                        delivery_id=claim.delivery_id,
                    )
                except CommunicationDeliveryLeaseLost:
                    if cancellation_after_finalize is not None:
                        raise cancellation_after_finalize
                    return self._lease_lost_outcome(claim, recovery)
                outcome = DeliveryRunOutcome(
                    outcome="sent",
                    delivery_id=claim.delivery_id,
                    attempts=claim.attempts,
                    recovered_retry_count=recovery.retry_count,
                    recovered_dead_count=recovery.dead_count,
                )
                if cancellation_after_finalize is not None:
                    raise cancellation_after_finalize
                return outcome

        outcome = await self._finish_terminal_despite_cancellation(
            self._record_failure(claim, result, recovery),
            delivery_id=claim.delivery_id,
        )
        if cancellation_after_finalize is not None:
            raise cancellation_after_finalize
        return outcome

    async def _recover_expired_leases(self) -> ExpiredLeaseRecoveryResult:
        async with self._session_factory() as session:
            recovery = await CommunicationDeliveryService.recover_expired_leases(
                session,
                channel=self._channel,
                limit=self._recovery_limit,
            )
            await session.commit()
            return recovery

    async def _claim_and_commit(self) -> ClaimedCommunicationDelivery | None:
        async with self._session_factory() as session:
            claim = await CommunicationDeliveryService.claim_next(
                session,
                worker_id=self._worker_id,
                channel=self._channel,
                lease_seconds=self._lease_seconds,
            )
            # This commit is deliberately before recipient lookup, rendering,
            # and every network operation. An uncommitted claim is never sent.
            await session.commit()
            return claim

    async def _recipient_is_current(self, claim: ClaimedCommunicationDelivery) -> bool:
        async with self._session_factory() as session:
            recipients = await ManagementRecipientDirectory.list_telegram(session)
        return any(
            recipient.recipient_key == claim.recipient_key
            and recipient.destination == claim.destination
            and recipient.channel == claim.channel
            for recipient in recipients
        )

    async def _cancel_inactive_recipient(self, claim: ClaimedCommunicationDelivery) -> None:
        async with self._session_factory() as session:
            await CommunicationDeliveryService.cancel_owned(
                session,
                delivery_id=claim.delivery_id,
                worker_id=self._worker_id,
                lease_token=claim.lease_token,
            )
            await session.commit()

    @staticmethod
    def _render(claim: ClaimedCommunicationDelivery) -> str:
        plan = CommunicationTemplatePlanV1(
            channel=claim.channel,
            audience="management",
            template_key=claim.template_key,
            template_version=claim.template_version,
            render_context=claim.render_context_dict(),
        )
        return WebsiteTemplateRegistry.render(plan)

    async def _send_with_heartbeat(
        self,
        claim: ClaimedCommunicationDelivery,
        rendered_text: str,
    ) -> ProviderDeliveryResult:
        stop_heartbeat = asyncio.Event()
        provider_task = asyncio.create_task(
            self._provider.send(
                destination=claim.destination,
                text=rendered_text,
                delivery_id=claim.delivery_id,
            )
        )
        heartbeat_task = asyncio.create_task(
            self._heartbeat(claim, stop_heartbeat)
        )
        try:
            done, _ = await asyncio.wait(
                {provider_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if provider_task.done():
                # A known provider result wins this local race. Heartbeat
                # errors are advisory now; the subsequent terminal transition
                # still has to pass the database lease fence.
                try:
                    result = await provider_task
                finally:
                    stop_heartbeat.set()
                    if heartbeat_task.done():
                        if heartbeat_task.cancelled():
                            logger.warning(
                                "Communication heartbeat canceled after provider result "
                                "delivery_id=%s",
                                claim.delivery_id,
                            )
                        else:
                            heartbeat_error = heartbeat_task.exception()
                            if heartbeat_error is not None:
                                logger.warning(
                                    "Communication heartbeat failed after provider result "
                                    "delivery_id=%s error_type=%s",
                                    claim.delivery_id,
                                    type(heartbeat_error).__name__,
                                )
                    else:
                        try:
                            await heartbeat_task
                        except Exception as exc:
                            logger.warning(
                                "Communication heartbeat failed after provider result "
                                "delivery_id=%s error_type=%s",
                                claim.delivery_id,
                                type(exc).__name__,
                            )
                return result

            if heartbeat_task in done:
                heartbeat_error = heartbeat_task.exception()
                if heartbeat_error is not None:
                    provider_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await provider_task
                    raise heartbeat_error
                provider_task.cancel()
                with suppress(asyncio.CancelledError):
                    await provider_task
                raise RuntimeError("Communication delivery heartbeat stopped early")

            raise RuntimeError("Communication delivery tasks stopped unexpectedly")
        except asyncio.CancelledError as cancellation:
            if provider_task.done() and not provider_task.cancelled():
                # A managed shutdown raced with a provider response that is
                # already known locally. Preserve it and let the database
                # terminal fence decide whether it may be recorded.
                stop_heartbeat.set()
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task
                logger.info(
                    "Communication cancellation deferred for known provider result "
                    "delivery_id=%s",
                    claim.delivery_id,
                )
                try:
                    completed_result = provider_task.result()
                except Exception as exc:
                    logger.warning(
                        "Communication provider raised during worker cancellation "
                        "delivery_id=%s error_type=%s",
                        claim.delivery_id,
                        type(exc).__name__,
                    )
                    completed_result = ProviderDeliveryResult.transient_failure(
                        category="provider",
                        code="provider_call_failed",
                        message="Communication provider failed unexpectedly",
                    )
                raise _ProviderResultDuringCancellation(
                    result=completed_result,
                    cancellation=cancellation,
                ) from cancellation
            provider_task.cancel()
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await provider_task
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            raise
        finally:
            stop_heartbeat.set()
            if not heartbeat_task.done():
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task

    async def _renew_before_send(self, claim: ClaimedCommunicationDelivery) -> None:
        async with self._session_factory() as session:
            await CommunicationDeliveryService.renew_lease(
                session,
                delivery_id=claim.delivery_id,
                worker_id=self._worker_id,
                lease_token=claim.lease_token,
                lease_seconds=self._lease_seconds,
            )
            await session.commit()

    @staticmethod
    async def _finish_terminal_despite_cancellation(
        operation: Coroutine[Any, Any, _TerminalResult],
        *,
        delivery_id: str,
    ) -> _TerminalResult:
        terminal_task = asyncio.create_task(operation)
        first_cancellation: asyncio.CancelledError | None = None
        while not terminal_task.done():
            try:
                await asyncio.shield(terminal_task)
            except asyncio.CancelledError as cancellation:
                if first_cancellation is None:
                    first_cancellation = cancellation

        try:
            result = terminal_task.result()
        except BaseException as terminal_error:
            if first_cancellation is None:
                raise
            logger.error(
                "Communication terminal finalize failed during cancellation "
                "delivery_id=%s error_type=%s",
                delivery_id,
                type(terminal_error).__name__,
            )
            raise first_cancellation from terminal_error

        if first_cancellation is not None:
            raise first_cancellation
        return result

    async def _heartbeat(
        self,
        claim: ClaimedCommunicationDelivery,
        stop: asyncio.Event,
    ) -> None:
        interval_seconds = max(1, min(15, self._lease_seconds // 3))
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
                return
            except TimeoutError:
                pass

            async with self._session_factory() as session:
                await CommunicationDeliveryService.renew_lease(
                    session,
                    delivery_id=claim.delivery_id,
                    worker_id=self._worker_id,
                    lease_token=claim.lease_token,
                    lease_seconds=self._lease_seconds,
                )
                await session.commit()

    async def _mark_sent(
        self,
        claim: ClaimedCommunicationDelivery,
        provider_message_id: str,
    ) -> None:
        async with self._session_factory() as session:
            await CommunicationDeliveryService.mark_sent(
                session,
                delivery_id=claim.delivery_id,
                worker_id=self._worker_id,
                lease_token=claim.lease_token,
                provider_message_id=provider_message_id,
            )
            await session.commit()

    async def _record_failure(
        self,
        claim: ClaimedCommunicationDelivery,
        result: ProviderDeliveryResult,
        recovery: ExpiredLeaseRecoveryResult,
    ) -> DeliveryRunOutcome:
        try:
            async with self._session_factory() as session:
                failure = await CommunicationDeliveryService.mark_failed(
                    session,
                    delivery_id=claim.delivery_id,
                    worker_id=self._worker_id,
                    lease_token=claim.lease_token,
                    result=result,
                )
                await session.commit()
        except CommunicationDeliveryLeaseLost:
            return self._lease_lost_outcome(claim, recovery)
        return self._failure_outcome(claim, failure, recovery)

    @staticmethod
    def _failure_outcome(
        claim: ClaimedCommunicationDelivery,
        failure: DeliveryFailureOutcome,
        recovery: ExpiredLeaseRecoveryResult,
    ) -> DeliveryRunOutcome:
        return DeliveryRunOutcome(
            outcome=failure.status,
            delivery_id=claim.delivery_id,
            attempts=failure.attempts,
            next_attempt_at=failure.next_attempt_at,
            recovered_retry_count=recovery.retry_count,
            recovered_dead_count=recovery.dead_count,
        )

    @staticmethod
    def _lease_lost_outcome(
        claim: ClaimedCommunicationDelivery,
        recovery: ExpiredLeaseRecoveryResult,
    ) -> DeliveryRunOutcome:
        return DeliveryRunOutcome(
            outcome="lease_lost",
            delivery_id=claim.delivery_id,
            attempts=claim.attempts,
            recovered_retry_count=recovery.retry_count,
            recovered_dead_count=recovery.dead_count,
        )
