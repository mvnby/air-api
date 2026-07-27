from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import CommunicationDelivery, CommunicationDeliveryAttempt
from services.communications.providers.base import (
    ProviderDeliveryDisposition,
    ProviderDeliveryResult,
)


class CommunicationDeliveryAttemptStateError(RuntimeError):
    pass


class CommunicationDeliveryAttemptService:
    """Transaction-neutral persistence for the PII-free attempt journal."""

    ERROR_CATEGORIES = frozenset(
        {
            "lease",
            "network",
            "payload",
            "provider",
            "rate_limit",
            "recipient",
            "template",
            "unknown",
        }
    )
    ERROR_CODES = frozenset(
        {
            "delivery_failed",
            "lease_expired",
            "lease_expired_after_provider",
            "lease_expired_before_provider",
            "provider_call_failed",
            "provider_result_invalid",
            "recipient_inactive",
            "runtime_control_fenced_before_provider",
            "telegram_api_error",
            "telegram_bad_request",
            "telegram_chat_migrated",
            "telegram_destination_invalid",
            "telegram_entity_too_large",
            "telegram_forbidden",
            "telegram_network_error",
            "telegram_provider_auth_or_conflict",
            "telegram_recipient_unavailable",
            "telegram_retry_after",
            "telegram_text_invalid",
            "telegram_transport_error",
            "telegram_unexpected_error",
            "template_render_failed",
            "timeout",
        }
    )
    FINAL_OUTCOMES = frozenset({"sent", "retry", "dead", "canceled"})
    ERROR_OUTCOMES = frozenset({"retry", "dead", "canceled"})

    @classmethod
    async def start(
        cls,
        session: AsyncSession,
        *,
        delivery: CommunicationDelivery,
        attempt_no: int,
        started_at: datetime,
    ) -> None:
        normalized_attempt_no = int(attempt_no)
        if normalized_attempt_no != int(delivery.attempts) + 1:
            raise CommunicationDeliveryAttemptStateError(
                f"Communication delivery {delivery.delivery_id!r} has an invalid attempt number"
            )
        existing = await session.get(
            CommunicationDeliveryAttempt,
            (delivery.delivery_id, normalized_attempt_no),
        )
        if existing is not None:
            raise CommunicationDeliveryAttemptStateError(
                f"Communication delivery {delivery.delivery_id!r} attempt "
                f"{normalized_attempt_no} already exists"
            )
        session.add(
            CommunicationDeliveryAttempt(
                delivery_id=delivery.delivery_id,
                attempt_no=normalized_attempt_no,
                started_at=started_at,
                outcome="running",
                ambiguous=False,
            )
        )

    @classmethod
    async def finish(
        cls,
        session: AsyncSession,
        *,
        delivery: CommunicationDelivery,
        finished_at: datetime,
        outcome: str,
        error_category: str | None = None,
        error_code: str | None = None,
        retry_after_seconds: int | None = None,
        provider_latency_ms: int | None = None,
        ambiguous: bool = False,
    ) -> None:
        attempt_no = int(delivery.attempts)
        statement = select(CommunicationDeliveryAttempt).where(
            CommunicationDeliveryAttempt.delivery_id == delivery.delivery_id,
            CommunicationDeliveryAttempt.attempt_no == attempt_no,
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update()
        attempt = (await session.execute(statement)).scalar_one_or_none()
        if (
            attempt is None
            or attempt.outcome != "running"
            or attempt.finished_at is not None
        ):
            raise CommunicationDeliveryAttemptStateError(
                f"Communication delivery {delivery.delivery_id!r} attempt "
                f"{attempt_no} is missing or already finalized"
            )

        normalized_outcome = str(outcome or "").strip().lower()
        if normalized_outcome not in cls.FINAL_OUTCOMES:
            raise ValueError("Communication delivery attempt outcome is invalid")
        normalized_latency = cls._normalize_provider_latency_ms(provider_latency_ms)
        normalized_retry_after = cls._normalize_retry_after_seconds(retry_after_seconds)
        if normalized_outcome not in {"retry", "dead"}:
            normalized_retry_after = None
        if normalized_outcome == "canceled":
            normalized_latency = None

        if normalized_outcome in cls.ERROR_OUTCOMES:
            normalized_error_category, normalized_error_code = cls._normalize_error(
                category=error_category,
                code=error_code,
            )
        else:
            normalized_error_category = None
            normalized_error_code = None

        attempt.finished_at = finished_at
        attempt.outcome = normalized_outcome
        attempt.error_category = normalized_error_category
        attempt.error_code = normalized_error_code
        attempt.retry_after_seconds = normalized_retry_after
        attempt.provider_latency_ms = normalized_latency
        attempt.ambiguous = bool(ambiguous)
        session.add(attempt)

    @classmethod
    async def mark_provider_started(
        cls,
        session: AsyncSession,
        *,
        delivery: CommunicationDelivery,
        started_at: datetime,
    ) -> None:
        """Persist the acceptance-ambiguity boundary for the current attempt."""

        attempt_no = int(delivery.attempts)
        statement = select(CommunicationDeliveryAttempt).where(
            CommunicationDeliveryAttempt.delivery_id == delivery.delivery_id,
            CommunicationDeliveryAttempt.attempt_no == attempt_no,
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update()
        attempt = (await session.execute(statement)).scalar_one_or_none()
        if (
            attempt is None
            or attempt.outcome != "running"
            or attempt.finished_at is not None
        ):
            raise CommunicationDeliveryAttemptStateError(
                f"Communication delivery {delivery.delivery_id!r} attempt "
                f"{attempt_no} is not running"
            )
        # Idempotency matters when the commit acknowledgement itself times out:
        # an already durable boundary is still safe to proceed from.
        if attempt.provider_started_at is None:
            attempt.provider_started_at = started_at
            session.add(attempt)

    @staticmethod
    def is_ambiguous_provider_failure(
        *,
        result: ProviderDeliveryResult,
        category: str,
        code: str,
    ) -> bool:
        normalized_category = str(category or "").strip().lower()
        normalized_code = str(code or "").strip().lower()
        if (
            result.disposition == ProviderDeliveryDisposition.AMBIGUOUS_FAILURE
            or normalized_code == "provider_result_invalid"
        ):
            return True
        return (
            result.disposition == ProviderDeliveryDisposition.TRANSIENT_FAILURE
            and normalized_category in {"network", "provider"}
        )

    @staticmethod
    def is_provably_retry_safe(
        *,
        result: ProviderDeliveryResult,
        category: str,
        code: str,
    ) -> bool:
        """Only retry outcomes that prove Telegram rejected before acceptance."""

        return (
            result.disposition == ProviderDeliveryDisposition.TRANSIENT_FAILURE
            and str(category or "").strip().lower() == "rate_limit"
            and str(code or "").strip().lower() == "telegram_retry_after"
            and result.retry_after_seconds is not None
            and int(result.retry_after_seconds) > 0
        )

    @classmethod
    def _normalize_error(
        cls,
        *,
        category: str | None,
        code: str | None,
    ) -> tuple[str, str]:
        normalized_category = str(category or "").strip().lower()
        if normalized_category not in cls.ERROR_CATEGORIES:
            normalized_category = "unknown"
        normalized_code = str(code or "").strip().lower()
        if normalized_code not in cls.ERROR_CODES:
            normalized_code = "delivery_failed"
        return normalized_category, normalized_code

    @staticmethod
    def _normalize_retry_after_seconds(value: int | None) -> int | None:
        if value is None:
            return None
        return max(1, min(int(value), 9_223_372_036_854_775_807))

    @staticmethod
    def _normalize_provider_latency_ms(value: int | None) -> int | None:
        if value is None:
            return None
        normalized = int(value)
        if normalized < 0:
            raise ValueError("Provider latency cannot be negative")
        return min(normalized, 9_223_372_036_854_775_807)
