from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import CommunicationDelivery, IntegrationOutboxEvent
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.canary_run_id import normalize_canary_run_id
from services.communications.contracts import (
    CommunicationRecipientV1,
    TelegramCanaryRequestedPayloadV1,
)
from services.communications.outbox_service import IntegrationOutboxService
from services.communications.recipient_directory import (
    OperationsCanaryRecipientDirectory,
)
from services.communications.template_registry import (
    TELEGRAM_CANARY_AGGREGATE_TYPE,
    TELEGRAM_CANARY_AGGREGATE_VERSION,
    TELEGRAM_CANARY_MAX_ATTEMPTS,
    TELEGRAM_CANARY_PRIORITY,
    TELEGRAM_CANARY_REQUESTED_EVENT,
    TELEGRAM_CANARY_TEMPLATE_KEY,
    telegram_canary_aggregate_id,
    telegram_canary_deduplication_key,
    telegram_canary_event_id,
    telegram_canary_idempotency_key,
)
from services.staff_user_service import StaffUserService


CANARY_AGGREGATE_TYPE = TELEGRAM_CANARY_AGGREGATE_TYPE
CANARY_AGGREGATE_VERSION = TELEGRAM_CANARY_AGGREGATE_VERSION
CANARY_PRIORITY = TELEGRAM_CANARY_PRIORITY
CANARY_MAX_ATTEMPTS = TELEGRAM_CANARY_MAX_ATTEMPTS


@dataclass(frozen=True)
class CommunicationsCanaryPreflight:
    recipients: tuple[CommunicationRecipientV1, CommunicationRecipientV1]

    @property
    def recipient_keys(self) -> tuple[str, str]:
        return (
            self.recipients[0].recipient_key,
            self.recipients[1].recipient_key,
        )


@dataclass(frozen=True)
class CommunicationsCanaryEnqueueResult:
    event: IntegrationOutboxEvent
    created: bool


@dataclass(frozen=True)
class CommunicationsCanaryLifecycle:
    state: Literal["pending", "ambiguous", "terminal"]
    terminal_outcome: Literal["success", "partial", "dead"] | None = None


class CommunicationsTelegramCanary:
    """Repeatable producer and privacy-safe inspection for bounded canary runs."""

    @staticmethod
    def normalize_run_id(run_id: str) -> str:
        try:
            return normalize_canary_run_id(run_id)
        except ValueError:
            raise CommunicationsCanarySafetyError("canary_run_id_invalid") from None

    @classmethod
    def event_id(cls, run_id: str) -> str:
        return telegram_canary_event_id(cls.normalize_run_id(run_id))

    @classmethod
    def _validate_event(
        cls,
        event: IntegrationOutboxEvent,
        *,
        run_id: str,
    ) -> TelegramCanaryRequestedPayloadV1:
        normalized_run_id = cls.normalize_run_id(run_id)
        try:
            payload = TelegramCanaryRequestedPayloadV1.model_validate(event.payload)
        except Exception:
            raise CommunicationsCanarySafetyError("canary_event_invalid") from None
        if (
            payload.run_id != normalized_run_id
            or event.event_id != cls.event_id(normalized_run_id)
            or event.event_type != TELEGRAM_CANARY_REQUESTED_EVENT
            or event.schema_version != 1
            or event.aggregate_type != CANARY_AGGREGATE_TYPE
            or event.aggregate_id != telegram_canary_aggregate_id(normalized_run_id)
            or event.aggregate_version != CANARY_AGGREGATE_VERSION
            or event.idempotency_key
            != telegram_canary_idempotency_key(normalized_run_id)
            or event.priority != CANARY_PRIORITY
            or event.max_attempts != CANARY_MAX_ATTEMPTS
            or event.attempts > CANARY_MAX_ATTEMPTS
            or event.actor_id is not None
            or event.correlation_id is not None
            or event.causation_id is not None
            or event.deduplication_key
            != telegram_canary_deduplication_key(normalized_run_id)
        ):
            raise CommunicationsCanarySafetyError("canary_event_invalid")
        return payload

    @staticmethod
    def validate_runtime(*, app_role: str | None, bot_token: str | None) -> None:
        if str(app_role or "").strip().lower() != "primary":
            raise CommunicationsCanarySafetyError("app_role_not_primary")
        normalized_token = str(bot_token or "").strip()
        if (
            not normalized_token
            or normalized_token == StaffUserService.DISABLED_BOT_TOKEN_PLACEHOLDER
        ):
            raise CommunicationsCanarySafetyError("telegram_bot_token_missing")

    @staticmethod
    async def assert_primary_writable_database(session: AsyncSession) -> None:
        try:
            bind = session.get_bind()
            dialect_name = str(getattr(bind.dialect, "name", "")).lower()
            if dialect_name != "postgresql":
                raise CommunicationsCanarySafetyError(
                    "database_dialect_not_postgresql"
                )
            recovery_result = await session.execute(text("SELECT pg_is_in_recovery()"))
            read_only_result = await session.execute(text("SHOW transaction_read_only"))
            in_recovery = bool(recovery_result.scalar())
            read_only = str(read_only_result.scalar() or "").strip().lower() in {
                "1",
                "on",
                "true",
                "yes",
            }
        except CommunicationsCanarySafetyError:
            raise
        except Exception:
            raise CommunicationsCanarySafetyError(
                "database_writability_unknown"
            ) from None
        if in_recovery or read_only:
            raise CommunicationsCanarySafetyError("database_not_writable_primary")

    @classmethod
    async def preflight_runtime(
        cls,
        session: AsyncSession,
        *,
        app_role: str | None,
        bot_token: str | None,
    ) -> None:
        cls.validate_runtime(app_role=app_role, bot_token=bot_token)
        await cls.assert_primary_writable_database(session)

    @classmethod
    async def preflight(
        cls,
        session: AsyncSession,
        *,
        app_role: str | None,
        bot_token: str | None,
    ) -> CommunicationsCanaryPreflight:
        await cls.preflight_runtime(
            session,
            app_role=app_role,
            bot_token=bot_token,
        )
        resolved = await OperationsCanaryRecipientDirectory.list_telegram(session)
        if len(resolved) != OperationsCanaryRecipientDirectory.EXPECTED_RECIPIENT_COUNT:
            raise CommunicationsCanarySafetyError(
                "active_owner_recipient_count_invalid"
            )
        recipients = (resolved[0], resolved[1])
        return CommunicationsCanaryPreflight(recipients=recipients)

    @classmethod
    async def enqueue(
        cls,
        session: AsyncSession,
        *,
        run_id: str,
        recipient_keys: Sequence[str],
        occurred_at: datetime | None = None,
    ) -> CommunicationsCanaryEnqueueResult:
        normalized_run_id = cls.normalize_run_id(run_id)
        payload = TelegramCanaryRequestedPayloadV1(
            run_id=normalized_run_id,
            recipient_keys=tuple(recipient_keys),
        )
        # Re-read the owner pair immediately before enqueue. The earlier CLI
        # preflight is not treated as an authorization cache.
        await OperationsCanaryRecipientDirectory.list_telegram(
            session,
            required_recipient_keys=payload.recipient_keys,
        )
        result = await IntegrationOutboxService.enqueue_with_result(
            session,
            event_type=TELEGRAM_CANARY_REQUESTED_EVENT,
            aggregate_type=CANARY_AGGREGATE_TYPE,
            aggregate_id=telegram_canary_aggregate_id(normalized_run_id),
            aggregate_version=CANARY_AGGREGATE_VERSION,
            idempotency_key=telegram_canary_idempotency_key(normalized_run_id),
            payload=payload,
            priority=CANARY_PRIORITY,
            max_attempts=CANARY_MAX_ATTEMPTS,
            occurred_at=occurred_at,
        )
        validated_payload = cls._validate_event(
            result.event,
            run_id=normalized_run_id,
        )
        if validated_payload.recipient_keys != payload.recipient_keys:
            raise CommunicationsCanarySafetyError("canary_snapshot_conflict")
        return CommunicationsCanaryEnqueueResult(
            event=result.event,
            created=result.created,
        )

    @classmethod
    def plan_snapshot(
        cls,
        preflight: CommunicationsCanaryPreflight,
        *,
        run_id: str,
        existing: IntegrationOutboxEvent | None,
    ) -> dict[str, Any]:
        normalized_run_id = cls.normalize_run_id(run_id)
        return {
            "mode": "plan",
            "run_id": normalized_run_id,
            "event_id": cls.event_id(normalized_run_id),
            "event_type": TELEGRAM_CANARY_REQUESTED_EVENT,
            "recipient_count": len(preflight.recipients),
            "recipient_keys": list(preflight.recipient_keys),
            "max_attempts": CANARY_MAX_ATTEMPTS,
            "existing": existing is not None,
            "existing_status": existing.status if existing is not None else None,
            "execute_would_create": existing is None,
            "will_enqueue": False,
            "will_send": False,
        }

    @classmethod
    async def assert_existing_snapshot_compatible(
        cls,
        session: AsyncSession,
        *,
        run_id: str,
        recipient_keys: tuple[str, str],
    ) -> IntegrationOutboxEvent | None:
        normalized_run_id = cls.normalize_run_id(run_id)
        event = await session.get(
            IntegrationOutboxEvent,
            cls.event_id(normalized_run_id),
        )
        if event is None:
            return None
        payload = cls._validate_event(event, run_id=normalized_run_id)
        if payload.recipient_keys != recipient_keys:
            raise CommunicationsCanarySafetyError("canary_snapshot_conflict")
        return event

    @classmethod
    async def _load_deliveries(
        cls,
        session: AsyncSession,
        *,
        event: IntegrationOutboxEvent,
        payload: TelegramCanaryRequestedPayloadV1,
    ) -> list[CommunicationDelivery]:
        deliveries = list(
            (
                await session.execute(
                    select(CommunicationDelivery)
                    .where(CommunicationDelivery.event_id == event.event_id)
                    .order_by(CommunicationDelivery.recipient_key.asc())
                )
            ).scalars()
        )
        expected_recipient_keys = set(payload.recipient_keys)
        expected_render_context = payload.model_dump(mode="json")
        if any(
            delivery.channel != "telegram"
            or delivery.template_key != TELEGRAM_CANARY_TEMPLATE_KEY
            or delivery.template_version != 1
            or delivery.max_attempts != CANARY_MAX_ATTEMPTS
            or delivery.recipient_key not in expected_recipient_keys
            or delivery.render_context != expected_render_context
            for delivery in deliveries
        ):
            raise CommunicationsCanarySafetyError("canary_delivery_invalid")
        return deliveries

    @staticmethod
    def _has_any_runtime_ownership(item: Any) -> bool:
        return bool(
            str(getattr(item, "worker_id", None) or "").strip()
            or str(getattr(item, "lease_token", None) or "").strip()
            or getattr(item, "lease_expires_at", None) is not None
        )

    @staticmethod
    def _has_valid_dispatcher_ownership(item: Any) -> bool:
        return bool(
            str(getattr(item, "worker_id", None) or "").strip()
            and not str(getattr(item, "lease_token", None) or "").strip()
            and getattr(item, "lease_expires_at", None) is None
        )

    @staticmethod
    def _has_complete_delivery_runtime_ownership(item: Any) -> bool:
        return bool(
            str(getattr(item, "worker_id", None) or "").strip()
            and str(getattr(item, "lease_token", None) or "").strip()
            and getattr(item, "lease_expires_at", None) is not None
        )

    @classmethod
    def _classify_lifecycle(
        cls,
        event: IntegrationOutboxEvent,
        deliveries: Sequence[CommunicationDelivery],
        *,
        expected_recipient_keys: Sequence[str],
    ) -> CommunicationsCanaryLifecycle:
        if event.status == "pending":
            return CommunicationsCanaryLifecycle(
                state=(
                    "ambiguous"
                    if deliveries or cls._has_any_runtime_ownership(event)
                    else "pending"
                )
            )
        if event.status == "processing":
            return CommunicationsCanaryLifecycle(
                state=(
                    "pending"
                    if not deliveries
                    and cls._has_valid_dispatcher_ownership(event)
                    else "ambiguous"
                )
            )
        if event.status == "dead":
            if deliveries or cls._has_any_runtime_ownership(event):
                return CommunicationsCanaryLifecycle(state="ambiguous")
            return CommunicationsCanaryLifecycle(
                state="terminal",
                terminal_outcome="dead",
            )
        actual_recipient_keys = [delivery.recipient_key for delivery in deliveries]
        if (
            event.status != "published"
            or len(deliveries) != 2
            or len(set(actual_recipient_keys)) != 2
            or set(actual_recipient_keys) != set(expected_recipient_keys)
            or cls._has_any_runtime_ownership(event)
        ):
            return CommunicationsCanaryLifecycle(state="ambiguous")

        statuses = {delivery.status for delivery in deliveries}
        if any(
            (
                delivery.status == "running"
                and not cls._has_complete_delivery_runtime_ownership(delivery)
            )
            or (
                delivery.status != "running"
                and cls._has_any_runtime_ownership(delivery)
            )
            for delivery in deliveries
        ):
            return CommunicationsCanaryLifecycle(state="ambiguous")
        known_statuses = {"queued", "running", "retry", "sent", "dead", "canceled"}
        if not statuses <= known_statuses:
            return CommunicationsCanaryLifecycle(state="ambiguous")
        if statuses & {"queued", "running", "retry"}:
            return CommunicationsCanaryLifecycle(state="pending")
        if statuses == {"sent"}:
            return CommunicationsCanaryLifecycle(
                state="terminal",
                terminal_outcome="success",
            )
        if "sent" in statuses:
            return CommunicationsCanaryLifecycle(
                state="terminal",
                terminal_outcome="partial",
            )
        if statuses <= {"dead", "canceled"}:
            return CommunicationsCanaryLifecycle(
                state="terminal",
                terminal_outcome="dead",
            )
        return CommunicationsCanaryLifecycle(state="ambiguous")

    @classmethod
    async def _inspect_lifecycle(
        cls,
        session: AsyncSession,
        *,
        event: IntegrationOutboxEvent,
        payload: TelegramCanaryRequestedPayloadV1,
    ) -> tuple[list[CommunicationDelivery], CommunicationsCanaryLifecycle]:
        deliveries = await cls._load_deliveries(
            session,
            event=event,
            payload=payload,
        )
        return deliveries, cls._classify_lifecycle(
            event,
            deliveries,
            expected_recipient_keys=payload.recipient_keys,
        )

    @classmethod
    async def execute_snapshot(
        cls,
        session: AsyncSession,
        preflight: CommunicationsCanaryPreflight,
        result: CommunicationsCanaryEnqueueResult,
        *,
        run_id: str,
    ) -> dict[str, Any]:
        normalized_run_id = cls.normalize_run_id(run_id)
        payload = cls._validate_event(result.event, run_id=normalized_run_id)
        _deliveries, lifecycle = await cls._inspect_lifecycle(
            session,
            event=result.event,
            payload=payload,
        )
        if result.created:
            if lifecycle.state != "pending":
                raise CommunicationsCanarySafetyError("canary_created_state_invalid")
            execution_result = "created"
        else:
            execution_result = f"replay_{lifecycle.state}"

        return {
            "mode": "execute",
            "run_id": normalized_run_id,
            "event_id": result.event.event_id,
            "event_type": result.event.event_type,
            "event_status": result.event.status,
            "execution_result": execution_result,
            "lifecycle": lifecycle.state,
            "terminal_outcome": lifecycle.terminal_outcome,
            "recipient_count": len(preflight.recipients),
            "recipient_keys": list(preflight.recipient_keys),
            "max_attempts": result.event.max_attempts,
            "created": result.created,
            "replay": not result.created,
            "accepted": result.created,
            "sent_directly": False,
        }

    @staticmethod
    def _timestamp(value: datetime | None) -> str | None:
        if value is None:
            return None
        normalized = value
        if normalized.tzinfo is None or normalized.utcoffset() is None:
            normalized = normalized.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @classmethod
    async def status_snapshot(
        cls,
        session: AsyncSession,
        *,
        run_id: str,
    ) -> dict[str, Any]:
        normalized_run_id = cls.normalize_run_id(run_id)
        event_id = cls.event_id(normalized_run_id)
        event = await session.get(IntegrationOutboxEvent, event_id)
        if event is None:
            return {
                "mode": "status",
                "run_id": normalized_run_id,
                "event_id": event_id,
                "found": False,
                "deliveries": [],
            }

        payload = cls._validate_event(event, run_id=normalized_run_id)
        deliveries, lifecycle = await cls._inspect_lifecycle(
            session,
            event=event,
            payload=payload,
        )
        return {
            "mode": "status",
            "run_id": normalized_run_id,
            "event_id": event.event_id,
            "found": True,
            "recipient_count": len(payload.recipient_keys),
            "recipient_keys": list(payload.recipient_keys),
            "status": event.status,
            "lifecycle": lifecycle.state,
            "terminal_outcome": lifecycle.terminal_outcome,
            "attempts": event.attempts,
            "max_attempts": event.max_attempts,
            "error_code": event.last_error_code,
            "timestamps": {
                "available_at": cls._timestamp(event.available_at),
                "occurred_at": cls._timestamp(event.occurred_at),
                "published_at": cls._timestamp(event.published_at),
                "created_at": cls._timestamp(event.created_at),
                "updated_at": cls._timestamp(event.updated_at),
            },
            "deliveries": [
                {
                    "delivery_id": delivery.delivery_id,
                    "recipient_key": delivery.recipient_key,
                    "status": delivery.status,
                    "attempts": delivery.attempts,
                    "max_attempts": delivery.max_attempts,
                    "provider_ack": bool(delivery.provider_message_id),
                    "error_code": delivery.last_error_code,
                    "timestamps": {
                        "available_at": cls._timestamp(delivery.available_at),
                        "sent_at": cls._timestamp(delivery.sent_at),
                        "finished_at": cls._timestamp(delivery.finished_at),
                        "created_at": cls._timestamp(delivery.created_at),
                        "updated_at": cls._timestamp(delivery.updated_at),
                    },
                }
                for delivery in deliveries
            ],
        }
