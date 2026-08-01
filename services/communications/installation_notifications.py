"""Typed safety control for tenant website Telegram notifications."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    CommunicationRuntimeState,
    IntegrationOutboxEvent,
    Storefront,
)
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.installation_activation_fence import (
    acquire_installation_activation_fence,
)
from services.communications.recipient_directory import (
    TenantWebsiteManagementRecipientDirectory,
)
from services.communications.runtime_config import CommunicationRuntimeConfig
from services.communications.runtime_state import (
    CommunicationRuntimeMode,
    CommunicationRuntimeStateService,
    CommunicationRuntimeStatus,
)
from services.communications.tenant_website_events import (
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    TENANT_WEBSITE_EVENT_TYPES,
)
from services.staff_user_service import StaffUserService


class InstallationNotificationControlRejected(RuntimeError):
    """Privacy-safe rejection suitable for operator output."""

    def __init__(self, error_code: str) -> None:
        self.error_code = str(error_code)
        super().__init__(self.error_code)


@dataclass(frozen=True)
class InstallationNotificationInspection:
    profile: str
    cutoff: datetime
    runtime_mode: str
    runtime_status: str
    control_revision: int
    activation_watermark: datetime | None
    owner_recipient_count: int
    runtime_lock_owner_count: int | None
    heartbeat_fresh: bool
    backlog_count: int
    running_count: int
    ambiguous_nonterminal_count: int
    ambiguous_terminal_count: int
    ambiguous_total_count: int
    outbox_status_counts: dict[str, int]
    delivery_status_counts: dict[str, int]
    attempt_outcome_counts: dict[str, int]
    provider_ack_count: int
    blockers: tuple[str, ...]

    @property
    def enable_allowed(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "cutoff": self.cutoff.isoformat(),
            "runtime_mode": self.runtime_mode,
            "runtime_status": self.runtime_status,
            "control_revision": self.control_revision,
            "activation_watermark": (
                self.activation_watermark.isoformat()
                if self.activation_watermark is not None
                else None
            ),
            "owner_recipient_count": self.owner_recipient_count,
            "runtime_lock_owner_count": self.runtime_lock_owner_count,
            "heartbeat_fresh": self.heartbeat_fresh,
            "backlog_count": self.backlog_count,
            "running_count": self.running_count,
            "ambiguous_nonterminal_count": self.ambiguous_nonterminal_count,
            "ambiguous_terminal_count": self.ambiguous_terminal_count,
            "ambiguous_total_count": self.ambiguous_total_count,
            "outbox_status_counts": dict(self.outbox_status_counts),
            "delivery_status_counts": dict(self.delivery_status_counts),
            "attempt_outcome_counts": dict(self.attempt_outcome_counts),
            "provider_ack_count": self.provider_ack_count,
            "enable_allowed": self.enable_allowed,
            "blockers": list(self.blockers),
        }


class InstallationNotificationOperations:
    """Inspect, activate, and emergency-disable the fixed website allowlist."""

    CHANNEL = "telegram"
    EVENT_TYPES = TENANT_WEBSITE_EVENT_TYPES
    # Compatibility export for the installation-specific operator surface.
    EVENT_TYPE = INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT
    NONTERMINAL_DELIVERY_STATUSES = ("queued", "retry", "running")
    DRAINED_RUNTIME_STATUSES = frozenset(
        {
            CommunicationRuntimeStatus.DISABLED.value,
            CommunicationRuntimeStatus.STOPPED.value,
            CommunicationRuntimeStatus.PAUSED.value,
            CommunicationRuntimeStatus.FAULTED.value,
        }
    )

    @staticmethod
    def deployment_profile(config: CommunicationRuntimeConfig) -> str:
        if config.enabled and config.allow_all_mode:
            return "active"
        if config.enabled and not config.allow_all_mode:
            return "canary"
        if not config.enabled and not config.allow_all_mode:
            return "dormant"
        return "invalid"

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    async def _database_primary_blocker(
        cls,
        session: AsyncSession,
    ) -> str | None:
        if session.get_bind().dialect.name != "postgresql":
            return "database_dialect_not_postgresql"
        try:
            async with session.begin_nested():
                row = (
                    await session.execute(
                        text(
                            "SELECT pg_is_in_recovery() AS in_recovery, "
                            "current_setting('transaction_read_only') AS read_only, "
                            "current_setting('transaction_isolation') "
                            "AS isolation_level"
                        )
                    )
                ).one()
        except Exception:
            return "database_writability_unknown"
        if bool(row.in_recovery) or str(row.read_only).strip().lower() != "off":
            return "database_not_writable_primary"
        if str(row.isolation_level).strip().lower() != "read committed":
            return "database_isolation_not_read_committed"
        return None

    @classmethod
    async def _runtime_lock_owner_count(
        cls,
        session: AsyncSession,
        *,
        lock_name: str,
    ) -> int | None:
        if session.get_bind().dialect.name != "postgresql":
            return None
        async with session.begin_nested():
            value = await session.scalar(
                text(
                    """
                    WITH lock_key AS (
                        SELECT hashtext(:lock_name)::bigint AS value
                    )
                    SELECT count(*)
                    FROM pg_locks, lock_key
                    WHERE locktype = 'advisory'
                      AND granted
                      AND classid = (((lock_key.value >> 32) & 4294967295)::oid)
                      AND objid = ((lock_key.value & 4294967295)::oid)
                      AND objsubid = 1
                    """
                ),
                {"lock_name": lock_name},
            )
        return int(value or 0)

    @classmethod
    async def _backlog_count(
        cls,
        session: AsyncSession,
        *,
        cutoff: datetime | None,
    ) -> int:
        nonterminal_delivery_exists = (
            select(CommunicationDelivery.delivery_id)
            .where(
                CommunicationDelivery.event_id
                == IntegrationOutboxEvent.event_id,
                CommunicationDelivery.status.in_(
                    cls.NONTERMINAL_DELIVERY_STATUSES
                ),
            )
            .exists()
        )
        statement = select(func.count(IntegrationOutboxEvent.event_id)).where(
            IntegrationOutboxEvent.event_type.in_(cls.EVENT_TYPES),
            or_(
                IntegrationOutboxEvent.status.in_(("pending", "processing")),
                nonterminal_delivery_exists,
            ),
        )
        if cutoff is not None:
            statement = statement.where(
                IntegrationOutboxEvent.created_at < cutoff
            )
        value = await session.scalar(statement)
        return int(value or 0)

    @classmethod
    async def _running_count(
        cls,
        session: AsyncSession,
        *,
        cutoff: datetime | None,
    ) -> int:
        statement = (
            select(
                func.count(func.distinct(CommunicationDelivery.delivery_id))
            )
            .join(
                IntegrationOutboxEvent,
                IntegrationOutboxEvent.event_id
                == CommunicationDelivery.event_id,
            )
            .outerjoin(
                CommunicationDeliveryAttempt,
                CommunicationDeliveryAttempt.delivery_id
                == CommunicationDelivery.delivery_id,
            )
            .where(
                IntegrationOutboxEvent.event_type.in_(cls.EVENT_TYPES),
                or_(
                    CommunicationDelivery.status == "running",
                    CommunicationDeliveryAttempt.outcome == "running",
                ),
            )
        )
        if cutoff is not None:
            statement = statement.where(
                IntegrationOutboxEvent.created_at < cutoff
            )
        return int((await session.scalar(statement)) or 0)

    @classmethod
    async def _ambiguous_count(
        cls,
        session: AsyncSession,
        *,
        cutoff: datetime | None,
        delivery_statuses: tuple[str, ...] | None = None,
    ) -> int:
        statement = (
            select(func.count(CommunicationDeliveryAttempt.delivery_id))
            .join(
                CommunicationDelivery,
                CommunicationDelivery.delivery_id
                == CommunicationDeliveryAttempt.delivery_id,
            )
            .join(
                IntegrationOutboxEvent,
                IntegrationOutboxEvent.event_id
                == CommunicationDelivery.event_id,
            )
            .where(
                IntegrationOutboxEvent.event_type.in_(cls.EVENT_TYPES),
                CommunicationDeliveryAttempt.ambiguous.is_(True),
            )
        )
        if cutoff is not None:
            statement = statement.where(
                IntegrationOutboxEvent.created_at < cutoff
            )
        if delivery_statuses is not None:
            statement = statement.where(
                CommunicationDelivery.status.in_(delivery_statuses)
            )
        return int((await session.scalar(statement)) or 0)

    @classmethod
    async def _status_counts(
        cls,
        session: AsyncSession,
    ) -> tuple[dict[str, int], dict[str, int], dict[str, int], int]:
        outbox_statuses = ("pending", "processing", "published", "dead")
        delivery_statuses = (
            "queued",
            "running",
            "retry",
            "sent",
            "dead",
            "canceled",
        )
        attempt_outcomes = ("running", "sent", "retry", "dead", "canceled")

        outbox_rows = (
            await session.execute(
                select(
                    IntegrationOutboxEvent.status,
                    func.count(IntegrationOutboxEvent.event_id),
                )
                .where(IntegrationOutboxEvent.event_type.in_(cls.EVENT_TYPES))
                .group_by(IntegrationOutboxEvent.status)
            )
        ).all()
        delivery_rows = (
            await session.execute(
                select(
                    CommunicationDelivery.status,
                    func.count(CommunicationDelivery.delivery_id),
                )
                .join(
                    IntegrationOutboxEvent,
                    IntegrationOutboxEvent.event_id
                    == CommunicationDelivery.event_id,
                )
                .where(IntegrationOutboxEvent.event_type.in_(cls.EVENT_TYPES))
                .group_by(CommunicationDelivery.status)
            )
        ).all()
        attempt_rows = (
            await session.execute(
                select(
                    CommunicationDeliveryAttempt.outcome,
                    func.count(),
                )
                .join(
                    CommunicationDelivery,
                    CommunicationDelivery.delivery_id
                    == CommunicationDeliveryAttempt.delivery_id,
                )
                .join(
                    IntegrationOutboxEvent,
                    IntegrationOutboxEvent.event_id
                    == CommunicationDelivery.event_id,
                )
                .where(IntegrationOutboxEvent.event_type.in_(cls.EVENT_TYPES))
                .group_by(CommunicationDeliveryAttempt.outcome)
            )
        ).all()
        provider_ack_count = int(
            (
                await session.scalar(
                    select(func.count(CommunicationDelivery.delivery_id))
                    .join(
                        IntegrationOutboxEvent,
                        IntegrationOutboxEvent.event_id
                        == CommunicationDelivery.event_id,
                    )
                    .where(
                        IntegrationOutboxEvent.event_type.in_(cls.EVENT_TYPES),
                        CommunicationDelivery.status == "sent",
                        CommunicationDelivery.provider_message_id.is_not(None),
                    )
                )
            )
            or 0
        )
        return (
            {
                status: int(dict(outbox_rows).get(status, 0))
                for status in outbox_statuses
            },
            {
                status: int(dict(delivery_rows).get(status, 0))
                for status in delivery_statuses
            },
            {
                outcome: int(dict(attempt_rows).get(outcome, 0))
                for outcome in attempt_outcomes
            },
            provider_ack_count,
        )

    @classmethod
    async def inspect(
        cls,
        session: AsyncSession,
        *,
        config: CommunicationRuntimeConfig,
        bot_token: str | None,
        runtime_locks_enabled: bool,
        cutoff: datetime | None = None,
        locked_state: CommunicationRuntimeState | None = None,
    ) -> InstallationNotificationInspection:
        inspection_time = cutoff or await CommunicationRuntimeStateService.database_now(
            session
        )
        inspection_time = CommunicationRuntimeStateService._as_utc(
            inspection_time
        )
        state = locked_state or await session.get(
            CommunicationRuntimeState,
            cls.CHANNEL,
        )
        blockers: list[str] = []
        profile = cls.deployment_profile(config)
        if profile != "active":
            blockers.append("communications_active_profile_required")
        if config.app_role != "primary":
            blockers.append("app_role_not_primary")
        normalized_token = str(bot_token or "").strip()
        if (
            not normalized_token
            or normalized_token
            == StaffUserService.DISABLED_BOT_TOKEN_PLACEHOLDER
        ):
            blockers.append("telegram_bot_token_missing")
        if not runtime_locks_enabled:
            blockers.append("runtime_database_locks_required")

        database_blocker = await cls._database_primary_blocker(session)
        if database_blocker is not None:
            blockers.append(database_blocker)

        owner_count = 0
        active_storefronts = list(
            (
                await session.execute(
                    select(Storefront)
                    .where(Storefront.status == "active")
                    .order_by(Storefront.tenant_id, Storefront.id)
                )
            ).scalars()
        )
        if not active_storefronts:
            blockers.append("tenant_website_storefront_count_invalid")
        for storefront in active_storefronts:
            try:
                recipients = (
                    await TenantWebsiteManagementRecipientDirectory.list_telegram(
                        session,
                        tenant_id=int(storefront.tenant_id),
                        storefront_id=int(storefront.id or 0),
                    )
                )
                if not recipients:
                    blockers.append("tenant_website_recipient_count_invalid")
                owner_count += len(recipients)
            except CommunicationsCanarySafetyError as error:
                blockers.append(error.error_code)

        runtime_mode = "missing"
        runtime_status = "missing"
        control_revision = 0
        watermark: datetime | None = None
        heartbeat_fresh = False
        if state is None:
            blockers.append("communications_runtime_state_missing")
        else:
            runtime_mode = str(state.mode)
            runtime_status = str(state.status)
            control_revision = int(state.control_revision)
            watermark = cls._as_utc(
                state.installation_estimate_watermark_at
            )
            if watermark is not None and watermark > inspection_time:
                blockers.append("installation_activation_watermark_invalid")
            if runtime_mode != CommunicationRuntimeMode.OFF.value:
                blockers.append("communications_runtime_mode_not_off")
            if runtime_status != CommunicationRuntimeStatus.DISABLED.value:
                blockers.append("communications_runtime_not_dormant")
            heartbeat = cls._as_utc(state.heartbeat_at)
            heartbeat_age = (
                (inspection_time - heartbeat).total_seconds()
                if heartbeat is not None
                else None
            )
            max_age = max(30.0, 3.0 * config.heartbeat_seconds)
            heartbeat_fresh = bool(
                state.instance_id
                and heartbeat_age is not None
                and 0 <= heartbeat_age <= max_age
            )
            if not heartbeat_fresh:
                blockers.append("communications_runtime_owner_not_fresh")

        try:
            lock_owner_count = await cls._runtime_lock_owner_count(
                session,
                lock_name=config.lock_name,
            )
        except Exception:
            lock_owner_count = None
            blockers.append("communications_runtime_lock_ownership_unknown")
        if lock_owner_count != 1:
            blockers.append("communications_runtime_owner_count_invalid")

        backlog_count = await cls._backlog_count(
            session,
            cutoff=None,
        )
        running_count = await cls._running_count(
            session,
            cutoff=None,
        )
        ambiguous_total = await cls._ambiguous_count(
            session,
            cutoff=None,
        )
        ambiguous_nonterminal = await cls._ambiguous_count(
            session,
            cutoff=None,
            delivery_statuses=cls.NONTERMINAL_DELIVERY_STATUSES,
        )
        ambiguous_terminal = max(
            0,
            ambiguous_total - ambiguous_nonterminal,
        )
        (
            outbox_status_counts,
            delivery_status_counts,
            attempt_outcome_counts,
            provider_ack_count,
        ) = await cls._status_counts(session)
        if backlog_count:
            blockers.append("installation_backlog_not_reconciled")
        if running_count:
            blockers.append("installation_delivery_running")
        if ambiguous_nonterminal:
            blockers.append("installation_ambiguous_outcomes_unreconciled")

        return InstallationNotificationInspection(
            profile=profile,
            cutoff=inspection_time,
            runtime_mode=runtime_mode,
            runtime_status=runtime_status,
            control_revision=control_revision,
            activation_watermark=watermark,
            owner_recipient_count=owner_count,
            runtime_lock_owner_count=lock_owner_count,
            heartbeat_fresh=heartbeat_fresh,
            backlog_count=backlog_count,
            running_count=running_count,
            ambiguous_nonterminal_count=ambiguous_nonterminal,
            ambiguous_terminal_count=ambiguous_terminal,
            ambiguous_total_count=ambiguous_total,
            outbox_status_counts=outbox_status_counts,
            delivery_status_counts=delivery_status_counts,
            attempt_outcome_counts=attempt_outcome_counts,
            provider_ack_count=provider_ack_count,
            blockers=tuple(dict.fromkeys(blockers)),
        )

    @classmethod
    async def activate_installation_from_off(
        cls,
        session: AsyncSession,
        *,
        config: CommunicationRuntimeConfig,
        bot_token: str | None,
        runtime_locks_enabled: bool,
    ) -> tuple[InstallationNotificationInspection, int, datetime]:
        """Atomically prove safety and arm the immutable ``all`` scope."""

        state = await CommunicationRuntimeStateService._lock_state(
            session,
            channel=cls.CHANNEL,
        )
        # Serialize with target event creation before reading the DB cutoff.
        # Fail fast instead of hanging an operator behind a stalled enqueue;
        # rerunning after that transaction finishes inventories its event.
        if not await acquire_installation_activation_fence(session):
            raise InstallationNotificationControlRejected(
                "installation_activation_fence_busy"
            )
        cutoff = await CommunicationRuntimeStateService.database_now(session)
        inspection = await cls.inspect(
            session,
            config=config,
            bot_token=bot_token,
            runtime_locks_enabled=runtime_locks_enabled,
            cutoff=cutoff,
            locked_state=state,
        )
        if inspection.blockers:
            raise InstallationNotificationControlRejected(
                inspection.blockers[0]
            )

        # This timestamp is a one-way event horizon. Emergency ``off`` retains
        # it, and a reviewed re-enable reuses it after proving the entire newer
        # backlog safe; no operator argument can move it backwards or forwards.
        watermark = inspection.activation_watermark or inspection.cutoff
        CommunicationRuntimeStateService._apply_control(
            state,
            mode=CommunicationRuntimeMode.ALL,
            canary_run_id=None,
            now=inspection.cutoff,
            installation_estimate_watermark_at=watermark,
        )
        await session.flush()
        return inspection, int(state.control_revision), watermark

    @classmethod
    async def wait_until_off_drained(
        cls,
        session_factory,
        *,
        wait_seconds: float = 30.0,
        poll_seconds: float = 0.25,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, min(float(wait_seconds), 60.0))
        while True:
            async with session_factory() as session:
                state = await session.get(
                    CommunicationRuntimeState,
                    cls.CHANNEL,
                )
                mode = str(state.mode) if state is not None else "missing"
                status = str(state.status) if state is not None else "missing"
                running_count = await cls._running_count(
                    session,
                    cutoff=None,
                )
                ambiguous_count = await cls._ambiguous_count(
                    session,
                    cutoff=None,
                )
                await session.rollback()
            drained = (
                mode == CommunicationRuntimeMode.OFF.value
                and status in cls.DRAINED_RUNTIME_STATUSES
                and running_count == 0
            )
            if drained or loop.time() >= deadline:
                return {
                    "drained": drained,
                    "runtime_mode": mode,
                    "runtime_status": status,
                    "running_delivery_count": running_count,
                    "ambiguous_total_count": ambiguous_count,
                }
            await asyncio.sleep(max(0.05, min(float(poll_seconds), 1.0)))
