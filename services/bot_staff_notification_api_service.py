"""API-owned staff notification delivery lifecycle for the autonomous bot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from models import OrderStageStatus, OrderWorkStage, StaffUser
from services.communications.delivery_service import (
    ClaimedCommunicationDelivery,
    CommunicationDeliveryLeaseLost,
    CommunicationDeliveryNotFound,
    CommunicationDeliveryService,
)
from services.communications.dispatcher import CommunicationOutboxDispatcher
from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.providers.base import ProviderDeliveryResult
from services.communications.staff_task_contracts import (
    StaffTaskNotificationPayloadV1,
)
from services.staff_user_service import StaffUserService


class BotStaffNotificationNotFoundError(LookupError):
    pass


class BotStaffNotificationLeaseConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class BotStaffNotificationMutationResult:
    delivery_id: str
    status: str
    lease_expires_at: datetime | None = None
    next_attempt_at: datetime | None = None


class BotStaffNotificationApiService:
    _SCOPE = CommunicationProcessingScope.staff_bot(control_revision=1)
    _MAX_DISPATCH_PER_CLAIM = 20
    _MAX_STALE_CLAIMS = 20

    @classmethod
    async def _materialize_pending(
        cls,
        session: AsyncSession,
        *,
        worker_id: str,
        now: datetime,
    ) -> None:
        await CommunicationDeliveryService.recover_expired_leases(
            session,
            scope=cls._SCOPE,
            channel="telegram",
            now=now,
        )
        await session.commit()
        for _ in range(cls._MAX_DISPATCH_PER_CLAIM):
            outcome = await CommunicationOutboxDispatcher.dispatch_next(
                session,
                dispatcher_id=f"{worker_id}:dispatch"[:128],
                scope=cls._SCOPE,
                now=now,
            )
            if outcome is None:
                break
            await session.commit()

    @staticmethod
    async def _claim_is_current(
        session: AsyncSession,
        claim: ClaimedCommunicationDelivery,
        payload: StaffTaskNotificationPayloadV1,
    ) -> bool:
        if claim.recipient_key != f"staff:{payload.staff_user_id}":
            return False
        staff_user = await session.get(StaffUser, payload.staff_user_id)
        if (
            staff_user is None
            or not StaffUserService.is_active(staff_user)
            or staff_user.telegram_id is None
            or str(int(staff_user.telegram_id)) != claim.destination
            or staff_user.legacy_installer_id is None
        ):
            return False
        stage = await session.get(OrderWorkStage, payload.stage_id)
        if (
            stage is None
            or int(stage.order_id) != payload.order_id
            or stage.installer_id != staff_user.legacy_installer_id
        ):
            return False
        stage_status = OrderStageStatus(stage.status)
        if payload.event_kind == "canceled":
            return stage_status == OrderStageStatus.CANCELED
        return stage_status not in {
            OrderStageStatus.CANCELED,
            OrderStageStatus.COMPLETED,
        }

    @classmethod
    async def claim(
        cls,
        session: AsyncSession,
        *,
        worker_id: str,
        visibility_timeout_seconds: int,
    ) -> dict | None:
        claim_time = await CommunicationDeliveryService.database_now(session)
        await cls._materialize_pending(
            session,
            worker_id=worker_id,
            now=claim_time,
        )
        for _ in range(cls._MAX_STALE_CLAIMS):
            claim = await CommunicationDeliveryService.claim_next(
                session,
                worker_id=worker_id,
                scope=cls._SCOPE,
                channel="telegram",
                lease_seconds=visibility_timeout_seconds,
                now=claim_time,
            )
            if claim is None:
                await session.commit()
                return None
            try:
                payload = StaffTaskNotificationPayloadV1.model_validate(
                    claim.render_context_dict()
                )
            except ValidationError:
                await CommunicationDeliveryService.cancel_owned(
                    session,
                    delivery_id=claim.delivery_id,
                    worker_id=worker_id,
                    lease_token=claim.lease_token,
                    error_category="contract",
                    error_code="invalid_staff_task_payload",
                    error_message="Staff task notification payload is invalid",
                    now=claim_time,
                )
                await session.commit()
                continue
            if not await cls._claim_is_current(session, claim, payload):
                await CommunicationDeliveryService.cancel_owned(
                    session,
                    delivery_id=claim.delivery_id,
                    worker_id=worker_id,
                    lease_token=claim.lease_token,
                    error_category="recipient",
                    error_code="staff_task_assignment_stale",
                    error_message="Staff task assignment is no longer current",
                    now=claim_time,
                )
                await session.commit()
                continue
            # Returning the payload to another process is the provider
            # ambiguity boundary: the remote bot may send successfully and
            # disappear before it can acknowledge this lease.
            lease_expires_at = (
                await CommunicationDeliveryService.mark_provider_started(
                    session,
                    delivery_id=claim.delivery_id,
                    worker_id=worker_id,
                    lease_token=claim.lease_token,
                    lease_seconds=visibility_timeout_seconds,
                )
            )
            await session.commit()
            return {
                "delivery_id": claim.delivery_id,
                "event_id": claim.event_id,
                "telegram_id": int(claim.destination),
                "payload": payload.model_dump(mode="json"),
                "attempt": claim.attempts,
                "max_attempts": claim.max_attempts,
                "lease_token": claim.lease_token,
                "lease_expires_at": lease_expires_at,
            }
        return None

    @staticmethod
    def _map_lifecycle_error(exc: Exception) -> Exception:
        if isinstance(exc, CommunicationDeliveryNotFound):
            return BotStaffNotificationNotFoundError(str(exc))
        if isinstance(exc, CommunicationDeliveryLeaseLost):
            return BotStaffNotificationLeaseConflictError(str(exc))
        return exc

    @classmethod
    async def renew(
        cls,
        session: AsyncSession,
        *,
        delivery_id: str,
        worker_id: str,
        lease_token: str,
        visibility_timeout_seconds: int,
    ) -> BotStaffNotificationMutationResult:
        try:
            expires_at = await CommunicationDeliveryService.renew_lease(
                session,
                delivery_id=delivery_id,
                worker_id=worker_id,
                lease_token=lease_token,
                lease_seconds=visibility_timeout_seconds,
            )
            await session.commit()
        except (CommunicationDeliveryNotFound, CommunicationDeliveryLeaseLost) as exc:
            await session.rollback()
            raise cls._map_lifecycle_error(exc) from exc
        return BotStaffNotificationMutationResult(
            delivery_id=delivery_id,
            status="running",
            lease_expires_at=expires_at,
        )

    @classmethod
    async def ack(
        cls,
        session: AsyncSession,
        *,
        delivery_id: str,
        worker_id: str,
        lease_token: str,
        telegram_message_id: int,
        provider_latency_ms: int | None,
    ) -> BotStaffNotificationMutationResult:
        try:
            await CommunicationDeliveryService.mark_sent(
                session,
                delivery_id=delivery_id,
                worker_id=worker_id,
                lease_token=lease_token,
                provider_message_id=f"telegram:{telegram_message_id}",
                provider_latency_ms=provider_latency_ms,
            )
            await session.commit()
        except (CommunicationDeliveryNotFound, CommunicationDeliveryLeaseLost) as exc:
            await session.rollback()
            raise cls._map_lifecycle_error(exc) from exc
        return BotStaffNotificationMutationResult(
            delivery_id=delivery_id,
            status="sent",
        )

    @classmethod
    async def nack(
        cls,
        session: AsyncSession,
        *,
        delivery_id: str,
        worker_id: str,
        lease_token: str,
        permanent: bool,
        error_code: str,
        retry_after_seconds: int | None,
    ) -> BotStaffNotificationMutationResult:
        if permanent:
            provider_result = ProviderDeliveryResult.permanent_failure(
                category="telegram",
                code=error_code,
                message="Telegram delivery failed permanently",
            )
        elif (
            error_code == "telegram_retry_after"
            and retry_after_seconds is not None
            and int(retry_after_seconds) > 0
        ):
            provider_result = ProviderDeliveryResult.transient_failure(
                category="rate_limit",
                code=error_code,
                message="Telegram rejected the request before acceptance",
                retry_after_seconds=retry_after_seconds,
            )
        else:
            provider_result = ProviderDeliveryResult.ambiguous_failure(
                category="provider",
                code=error_code,
                message="Telegram delivery outcome requires manual reconciliation",
            )
        try:
            outcome = await CommunicationDeliveryService.mark_failed(
                session,
                delivery_id=delivery_id,
                worker_id=worker_id,
                lease_token=lease_token,
                result=provider_result,
            )
            await session.commit()
        except (CommunicationDeliveryNotFound, CommunicationDeliveryLeaseLost) as exc:
            await session.rollback()
            raise cls._map_lifecycle_error(exc) from exc
        return BotStaffNotificationMutationResult(
            delivery_id=delivery_id,
            status=outcome.status,
            next_attempt_at=outcome.next_attempt_at,
        )
