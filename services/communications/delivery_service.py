from __future__ import annotations

import hashlib
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import MappingProxyType

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import CommunicationDelivery
from services.communications.delivery_attempt_service import (
    CommunicationDeliveryAttemptService,
)
from services.communications.delivery_limits import (
    MAX_DELIVERY_LEASE_SECONDS,
    MIN_DELIVERY_LEASE_SECONDS,
)
from services.communications.providers.base import (
    ProviderDeliveryDisposition,
    ProviderDeliveryResult,
)

DELIVERY_STATUS_QUEUED = "queued"
DELIVERY_STATUS_RUNNING = "running"
DELIVERY_STATUS_RETRY = "retry"
DELIVERY_STATUS_SENT = "sent"
DELIVERY_STATUS_DEAD = "dead"
DELIVERY_STATUS_CANCELED = "canceled"


class CommunicationDeliveryNotFound(LookupError):
    pass


class CommunicationDeliveryLeaseLost(RuntimeError):
    pass


def _freeze_json_value(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType(
            {str(key): _freeze_json_value(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json_value(item) for item in value)
    return value


def _thaw_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json_value(item) for item in value]
    return value


@dataclass(frozen=True)
class ClaimedCommunicationDelivery:
    delivery_id: str
    event_id: str
    channel: str
    recipient_key: str = field(repr=False)
    destination: str = field(repr=False)
    template_key: str
    template_version: int
    render_context: Mapping[str, object] = field(repr=False)
    attempts: int
    max_attempts: int
    lease_token: str = field(repr=False)
    lease_expires_at: datetime

    def render_context_dict(self) -> dict[str, object]:
        thawed = _thaw_json_value(self.render_context)
        if not isinstance(thawed, dict):
            raise TypeError("Communication delivery render context must be an object")
        return thawed


@dataclass(frozen=True)
class ExpiredLeaseRecoveryResult:
    retry_count: int
    dead_count: int


@dataclass(frozen=True)
class DeliveryFailureOutcome:
    status: str
    attempts: int
    next_attempt_at: datetime | None


class CommunicationDeliveryService:
    """Transaction-neutral state machine for one immutable recipient delivery."""

    MIN_LEASE_SECONDS = MIN_DELIVERY_LEASE_SECONDS
    MAX_LEASE_SECONDS = MAX_DELIVERY_LEASE_SECONDS
    MAX_RECOVERY_LIMIT = 1000
    RETRY_BASE_SECONDS = 30
    RETRY_MAX_SECONDS = 3600
    RETRY_JITTER_PERCENT = 20

    @classmethod
    async def claim_next(
        cls,
        session: AsyncSession,
        *,
        worker_id: str,
        channel: str = "telegram",
        lease_seconds: int = 90,
        now: datetime | None = None,
    ) -> ClaimedCommunicationDelivery | None:
        normalized_worker_id = cls._normalize_worker_id(worker_id)
        normalized_channel = cls._normalize_channel(channel)
        lease_duration = cls._normalize_lease_seconds(lease_seconds)
        claimed_at = await cls._resolve_now(session, now)

        statement = (
            select(CommunicationDelivery)
            .where(
                CommunicationDelivery.channel == normalized_channel,
                CommunicationDelivery.status.in_(
                    [DELIVERY_STATUS_QUEUED, DELIVERY_STATUS_RETRY]
                ),
                CommunicationDelivery.available_at <= claimed_at,
                CommunicationDelivery.attempts < CommunicationDelivery.max_attempts,
            )
            .order_by(
                CommunicationDelivery.priority.asc(),
                CommunicationDelivery.available_at.asc(),
                CommunicationDelivery.created_at.asc(),
                CommunicationDelivery.delivery_id.asc(),
            )
            .limit(1)
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)

        delivery = (await session.execute(statement)).scalar_one_or_none()
        if delivery is None:
            return None

        lease_token = secrets.token_urlsafe(32)
        lease_expires_at = claimed_at + timedelta(seconds=lease_duration)
        next_attempt_no = int(delivery.attempts) + 1
        await CommunicationDeliveryAttemptService.start(
            session,
            delivery=delivery,
            attempt_no=next_attempt_no,
            started_at=claimed_at,
        )
        delivery.status = DELIVERY_STATUS_RUNNING
        delivery.attempts = next_attempt_no
        delivery.worker_id = normalized_worker_id
        delivery.lease_token = lease_token
        delivery.lease_expires_at = lease_expires_at
        delivery.last_error_category = None
        delivery.last_error_code = None
        delivery.last_error_message = None
        delivery.sent_at = None
        delivery.finished_at = None
        delivery.updated_at = claimed_at
        session.add(delivery)
        await session.flush()

        return ClaimedCommunicationDelivery(
            delivery_id=delivery.delivery_id,
            event_id=delivery.event_id,
            channel=delivery.channel,
            recipient_key=delivery.recipient_key,
            destination=delivery.destination,
            template_key=delivery.template_key,
            template_version=delivery.template_version,
            render_context=_freeze_json_value(dict(delivery.render_context or {})),
            attempts=delivery.attempts,
            max_attempts=delivery.max_attempts,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
        )

    @classmethod
    async def recover_expired_leases(
        cls,
        session: AsyncSession,
        *,
        channel: str = "telegram",
        now: datetime | None = None,
        limit: int = 100,
    ) -> ExpiredLeaseRecoveryResult:
        normalized_channel = cls._normalize_channel(channel)
        recovered_at = await cls._resolve_now(session, now)
        safe_limit = max(1, min(cls.MAX_RECOVERY_LIMIT, int(limit)))
        statement = (
            select(CommunicationDelivery)
            .where(
                CommunicationDelivery.channel == normalized_channel,
                CommunicationDelivery.status == DELIVERY_STATUS_RUNNING,
                CommunicationDelivery.lease_expires_at.is_not(None),
                CommunicationDelivery.lease_expires_at <= recovered_at,
            )
            .order_by(
                CommunicationDelivery.lease_expires_at.asc(),
                CommunicationDelivery.created_at.asc(),
                CommunicationDelivery.delivery_id.asc(),
            )
            .limit(safe_limit)
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)

        deliveries = list((await session.execute(statement)).scalars().all())
        retry_count = 0
        dead_count = 0
        for delivery in deliveries:
            await CommunicationDeliveryAttemptService.finish(
                session,
                delivery=delivery,
                finished_at=recovered_at,
                outcome=(
                    DELIVERY_STATUS_DEAD
                    if int(delivery.attempts) >= int(delivery.max_attempts)
                    else DELIVERY_STATUS_RETRY
                ),
                error_category="lease",
                error_code="lease_expired",
                ambiguous=True,
            )
            delivery.worker_id = None
            delivery.lease_token = None
            delivery.lease_expires_at = None
            delivery.last_error_category = "lease"
            delivery.last_error_code = "lease_expired"
            delivery.last_error_message = "Delivery worker lease expired before completion"
            delivery.updated_at = recovered_at
            if int(delivery.attempts) >= int(delivery.max_attempts):
                delivery.status = DELIVERY_STATUS_DEAD
                delivery.sent_at = None
                delivery.finished_at = recovered_at
                dead_count += 1
            else:
                delivery.status = DELIVERY_STATUS_RETRY
                delivery.available_at = recovered_at + timedelta(
                    seconds=cls.retry_delay_seconds(
                        delivery_id=delivery.delivery_id,
                        attempts=delivery.attempts,
                    )
                )
                delivery.sent_at = None
                delivery.finished_at = None
                retry_count += 1
            session.add(delivery)

        await session.flush()
        return ExpiredLeaseRecoveryResult(
            retry_count=retry_count,
            dead_count=dead_count,
        )

    @classmethod
    async def renew_lease(
        cls,
        session: AsyncSession,
        *,
        delivery_id: str,
        worker_id: str,
        lease_token: str,
        lease_seconds: int = 90,
        now: datetime | None = None,
    ) -> datetime:
        delivery, renewed_at = await cls._lock_owned_delivery(
            session,
            delivery_id=delivery_id,
            worker_id=worker_id,
            lease_token=lease_token,
            now=now,
        )
        lease_expires_at = renewed_at + timedelta(
            seconds=cls._normalize_lease_seconds(lease_seconds)
        )
        delivery.lease_expires_at = lease_expires_at
        delivery.updated_at = renewed_at
        session.add(delivery)
        await session.flush()
        return lease_expires_at

    @classmethod
    async def mark_sent(
        cls,
        session: AsyncSession,
        *,
        delivery_id: str,
        worker_id: str,
        lease_token: str,
        provider_message_id: str,
        provider_latency_ms: int | None = None,
        now: datetime | None = None,
    ) -> None:
        normalized_message_id = str(provider_message_id or "").strip()
        if not normalized_message_id:
            raise ValueError("Provider message ID is required")
        if len(normalized_message_id) > 255:
            raise ValueError("Provider message ID exceeds 255 characters")

        delivery, completed_at = await cls._lock_owned_delivery(
            session,
            delivery_id=delivery_id,
            worker_id=worker_id,
            lease_token=lease_token,
            now=now,
        )
        await CommunicationDeliveryAttemptService.finish(
            session,
            delivery=delivery,
            finished_at=completed_at,
            outcome=DELIVERY_STATUS_SENT,
            provider_latency_ms=provider_latency_ms,
        )
        delivery.status = DELIVERY_STATUS_SENT
        delivery.provider_message_id = normalized_message_id
        delivery.last_error_category = None
        delivery.last_error_code = None
        delivery.last_error_message = None
        delivery.sent_at = completed_at
        delivery.finished_at = completed_at
        delivery.worker_id = None
        delivery.lease_token = None
        delivery.lease_expires_at = None
        delivery.updated_at = completed_at
        session.add(delivery)
        await session.flush()

    @classmethod
    async def mark_failed(
        cls,
        session: AsyncSession,
        *,
        delivery_id: str,
        worker_id: str,
        lease_token: str,
        result: ProviderDeliveryResult,
        provider_latency_ms: int | None = None,
        now: datetime | None = None,
    ) -> DeliveryFailureOutcome:
        if result.disposition == ProviderDeliveryDisposition.SENT:
            raise ValueError("A sent provider result cannot be recorded as a failure")

        delivery, failed_at = await cls._lock_owned_delivery(
            session,
            delivery_id=delivery_id,
            worker_id=worker_id,
            lease_token=lease_token,
            now=now,
        )
        category, code, message = cls._sanitize_provider_error(result)
        terminal = (
            result.disposition == ProviderDeliveryDisposition.PERMANENT_FAILURE
            or int(delivery.attempts) >= int(delivery.max_attempts)
        )
        next_attempt_at: datetime | None = None
        if terminal:
            failure_status = DELIVERY_STATUS_DEAD
        else:
            retry_delay = cls.retry_delay_seconds(
                delivery_id=delivery.delivery_id,
                attempts=delivery.attempts,
            )
            if result.retry_after_seconds is not None:
                retry_delay = max(
                    retry_delay,
                    max(1, int(result.retry_after_seconds)),
                )
            next_attempt_at = failed_at + timedelta(seconds=retry_delay)
            failure_status = DELIVERY_STATUS_RETRY

        await CommunicationDeliveryAttemptService.finish(
            session,
            delivery=delivery,
            finished_at=failed_at,
            outcome=failure_status,
            error_category=category,
            error_code=code,
            retry_after_seconds=result.retry_after_seconds,
            provider_latency_ms=provider_latency_ms,
            ambiguous=CommunicationDeliveryAttemptService.is_ambiguous_provider_failure(
                result=result,
                category=category,
                code=code,
            ),
        )

        delivery.status = failure_status
        delivery.last_error_category = category
        delivery.last_error_code = code
        delivery.last_error_message = message
        delivery.provider_message_id = None
        delivery.sent_at = None
        delivery.finished_at = failed_at if terminal else None
        delivery.worker_id = None
        delivery.lease_token = None
        delivery.lease_expires_at = None
        delivery.updated_at = failed_at
        if next_attempt_at is not None:
            delivery.available_at = next_attempt_at
        session.add(delivery)
        await session.flush()
        return DeliveryFailureOutcome(
            status=delivery.status,
            attempts=delivery.attempts,
            next_attempt_at=next_attempt_at,
        )

    @classmethod
    async def cancel_owned(
        cls,
        session: AsyncSession,
        *,
        delivery_id: str,
        worker_id: str,
        lease_token: str,
        error_category: str = "recipient",
        error_code: str = "recipient_inactive",
        error_message: str = "Communication recipient is no longer eligible",
        now: datetime | None = None,
    ) -> None:
        delivery, canceled_at = await cls._lock_owned_delivery(
            session,
            delivery_id=delivery_id,
            worker_id=worker_id,
            lease_token=lease_token,
            now=now,
        )
        normalized_error_category = cls._sanitize_text(
            error_category,
            80,
            "recipient",
        )
        normalized_error_code = cls._sanitize_text(
            error_code,
            100,
            "recipient_inactive",
        )
        await CommunicationDeliveryAttemptService.finish(
            session,
            delivery=delivery,
            finished_at=canceled_at,
            outcome=DELIVERY_STATUS_CANCELED,
            error_category=normalized_error_category,
            error_code=normalized_error_code,
        )
        delivery.status = DELIVERY_STATUS_CANCELED
        delivery.provider_message_id = None
        delivery.last_error_category = normalized_error_category
        delivery.last_error_code = normalized_error_code
        delivery.last_error_message = cls._sanitize_text(
            error_message,
            1000,
            "Communication recipient is no longer eligible",
        )
        delivery.sent_at = None
        delivery.finished_at = canceled_at
        delivery.worker_id = None
        delivery.lease_token = None
        delivery.lease_expires_at = None
        delivery.updated_at = canceled_at
        session.add(delivery)
        await session.flush()

    @classmethod
    def retry_delay_seconds(cls, *, delivery_id: str, attempts: int) -> int:
        safe_attempts = max(1, int(attempts))
        exponential_delay = min(
            cls.RETRY_MAX_SECONDS,
            cls.RETRY_BASE_SECONDS * (2 ** min(safe_attempts - 1, 16)),
        )
        if exponential_delay >= cls.RETRY_MAX_SECONDS:
            return cls.RETRY_MAX_SECONDS
        jitter_window = max(
            1,
            (exponential_delay * cls.RETRY_JITTER_PERCENT) // 100,
        )
        digest = hashlib.sha256(
            f"{delivery_id}:{safe_attempts}".encode("utf-8")
        ).digest()
        return min(
            cls.RETRY_MAX_SECONDS,
            exponential_delay + int.from_bytes(digest[:4], "big") % (jitter_window + 1),
        )

    @classmethod
    async def _lock_owned_delivery(
        cls,
        session: AsyncSession,
        *,
        delivery_id: str,
        worker_id: str,
        lease_token: str,
        now: datetime | None,
    ) -> tuple[CommunicationDelivery, datetime]:
        normalized_delivery_id = cls._normalize_delivery_id(delivery_id)
        normalized_worker_id = cls._normalize_worker_id(worker_id)
        normalized_lease_token = cls._normalize_lease_token(lease_token)
        explicit_now = cls._normalize_now(now) if now is not None else None
        statement = select(CommunicationDelivery).where(
            CommunicationDelivery.delivery_id == normalized_delivery_id,
            CommunicationDelivery.status == DELIVERY_STATUS_RUNNING,
            CommunicationDelivery.worker_id == normalized_worker_id,
            CommunicationDelivery.lease_token == normalized_lease_token,
            CommunicationDelivery.lease_expires_at.is_not(None),
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update()
        delivery = (await session.execute(statement)).scalar_one_or_none()
        if delivery is not None:
            locked_at = explicit_now or await cls._database_now(session)
            lease_expires_at = cls._coerce_database_datetime(
                delivery.lease_expires_at
            )
            if lease_expires_at <= locked_at:
                raise CommunicationDeliveryLeaseLost(
                    f"Communication delivery {normalized_delivery_id!r} lease expired"
                )
            return delivery, locked_at

        exists = await session.get(CommunicationDelivery, normalized_delivery_id)
        if exists is None:
            raise CommunicationDeliveryNotFound(
                f"Communication delivery {normalized_delivery_id!r} was not found"
            )
        raise CommunicationDeliveryLeaseLost(
            f"Communication delivery {normalized_delivery_id!r} lease is no longer owned"
        )

    @classmethod
    async def _resolve_now(
        cls,
        session: AsyncSession,
        value: datetime | None,
    ) -> datetime:
        if value is not None:
            return cls._normalize_now(value)
        return await cls._database_now(session)

    @classmethod
    async def _database_now(cls, session: AsyncSession) -> datetime:
        clock = (
            func.clock_timestamp()
            if session.get_bind().dialect.name == "postgresql"
            else func.current_timestamp()
        )
        value = (await session.execute(select(clock))).scalar_one()
        return cls._coerce_database_datetime(value)

    @staticmethod
    def _coerce_database_datetime(value: object) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace(" ", "T"))
        if not isinstance(value, datetime):
            raise TypeError("Database clock did not return a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _normalize_now(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Communication delivery timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _normalize_delivery_id(delivery_id: str) -> str:
        normalized = str(delivery_id or "").strip()
        if not re.fullmatch(r"[0-9a-f]{32}", normalized):
            raise ValueError("Communication delivery ID must be 32 lowercase hex characters")
        return normalized

    @staticmethod
    def _normalize_worker_id(worker_id: str) -> str:
        normalized = str(worker_id or "").strip()
        if not normalized:
            raise ValueError("Communication delivery worker ID is required")
        if len(normalized) > 128:
            raise ValueError("Communication delivery worker ID exceeds 128 characters")
        return normalized

    @staticmethod
    def _normalize_lease_token(lease_token: str) -> str:
        normalized = str(lease_token or "").strip()
        if len(normalized) < 32 or len(normalized) > 255:
            raise ValueError("Communication delivery lease token is invalid")
        return normalized

    @staticmethod
    def _normalize_channel(channel: str) -> str:
        normalized = str(channel or "").strip().lower()
        if not normalized or len(normalized) > 32:
            raise ValueError("Communication delivery channel is invalid")
        return normalized

    @classmethod
    def _normalize_lease_seconds(cls, lease_seconds: int) -> int:
        normalized = int(lease_seconds)
        if not cls.MIN_LEASE_SECONDS <= normalized <= cls.MAX_LEASE_SECONDS:
            raise ValueError(
                f"Communication delivery lease must be between "
                f"{cls.MIN_LEASE_SECONDS} and {cls.MAX_LEASE_SECONDS} seconds"
            )
        return normalized

    @classmethod
    def _sanitize_provider_error(
        cls,
        result: ProviderDeliveryResult,
    ) -> tuple[str, str, str]:
        return (
            cls._sanitize_text(result.error_category, 80, "provider"),
            cls._sanitize_text(result.error_code, 100, "delivery_failed"),
            cls._sanitize_text(
                result.error_message,
                1000,
                "Communication delivery failed",
            ),
        )

    @staticmethod
    def _sanitize_text(value: str | None, limit: int, fallback: str) -> str:
        normalized = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
        normalized = " ".join(normalized.split()).strip()
        return (normalized or fallback)[:limit]
