"""Fail-closed reconciliation for stale installation-estimate communications.

Dry-run inventory is privacy-safe and may run against a local SQLite database.
Execution is deliberately stricter: the caller must hold the managed Telegram
runtime advisory lock, and this transaction must prove that it is running on
the writable PostgreSQL primary while the durable runtime is stopped and off.

The caller owns commit/rollback and must keep the advisory lock until that
transaction is finished.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    CommunicationRuntimeState,
    IntegrationOutboxEvent,
)
from services.communications.backlog_reconciliation_contracts import (
    MAX_RECONCILIATION_ATTEMPTS,
    MAX_RECONCILIATION_DELIVERIES,
    MAX_RECONCILIATION_LIMIT,
    NON_TERMINAL_DELIVERY_STATUSES,
    STALE_BACKLOG_ERROR_CATEGORY,
    STALE_BACKLOG_ERROR_CODE,
    STALE_BACKLOG_ERROR_MESSAGE,
    InstallationEstimateBacklogExecutionBlocked,
    InstallationEstimateBacklogReport,
)
from services.communications.canary import CommunicationsTelegramCanary
from services.communications.canary_errors import CommunicationsCanarySafetyError
from services.communications.runtime_config import CommunicationRuntimeConfig
from services.communications.runtime_state import (
    CommunicationRuntimeMode,
    CommunicationRuntimeStateService,
    CommunicationRuntimeStatus,
)
from services.communications.template_registry import (
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    INSTALLATION_ESTIMATE_TEMPLATE_KEY,
)
from services.runtime_lock_service import RuntimeLock


class InstallationEstimateBacklogReconciliation:
    """Inventory and terminally suppress a bounded stale website backlog."""

    EVENT_TYPE = INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT
    TEMPLATE_KEY = INSTALLATION_ESTIMATE_TEMPLATE_KEY
    CHANNEL = "telegram"

    @staticmethod
    def _normalize_cutoff(cutoff: datetime, *, now: datetime) -> datetime:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("cutoff must include a timezone")
        normalized = cutoff.astimezone(timezone.utc)
        normalized_now = now.astimezone(timezone.utc)
        if normalized >= normalized_now:
            raise ValueError("cutoff must be earlier than now")
        return normalized

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit must be an integer")
        if limit < 1 or limit > MAX_RECONCILIATION_LIMIT:
            raise ValueError(
                f"limit must be between 1 and {MAX_RECONCILIATION_LIMIT}"
            )
        return limit

    @classmethod
    def _candidate_predicates(cls, *, cutoff: datetime) -> tuple[Any, ...]:
        nonterminal_delivery_exists = (
            select(CommunicationDelivery.delivery_id)
            .where(
                CommunicationDelivery.event_id
                == IntegrationOutboxEvent.event_id,
                CommunicationDelivery.status.in_(
                    tuple(NON_TERMINAL_DELIVERY_STATUSES)
                ),
            )
            .exists()
        )
        return (
            IntegrationOutboxEvent.event_type == cls.EVENT_TYPE,
            IntegrationOutboxEvent.created_at < cutoff,
            or_(
                IntegrationOutboxEvent.status == "pending",
                # A dispatcher interrupted before terminal publication can
                # otherwise be recovered and sent after activation.
                IntegrationOutboxEvent.status == "processing",
                and_(
                    IntegrationOutboxEvent.status == "published",
                    nonterminal_delivery_exists,
                ),
            ),
        )

    @classmethod
    async def _candidate_total(
        cls,
        session: AsyncSession,
        *,
        cutoff: datetime,
    ) -> int:
        value = await session.scalar(
            select(func.count(IntegrationOutboxEvent.event_id)).where(
                *cls._candidate_predicates(cutoff=cutoff)
            )
        )
        return int(value or 0)

    @classmethod
    async def _select_candidates(
        cls,
        session: AsyncSession,
        *,
        cutoff: datetime,
        limit: int,
        lock: bool,
    ) -> list[IntegrationOutboxEvent]:
        query = (
            select(IntegrationOutboxEvent)
            .where(*cls._candidate_predicates(cutoff=cutoff))
            .order_by(
                IntegrationOutboxEvent.created_at.asc(),
                IntegrationOutboxEvent.event_id.asc(),
            )
            .limit(limit)
        )
        if lock:
            query = query.with_for_update(skip_locked=True)
        return list((await session.execute(query)).scalars())

    @staticmethod
    async def _load_deliveries(
        session: AsyncSession,
        event_ids: tuple[str, ...],
        *,
        lock: bool,
    ) -> tuple[list[CommunicationDelivery], int, bool]:
        if not event_ids:
            return [], 0, False
        total = int(
            (
                await session.scalar(
                    select(func.count(CommunicationDelivery.delivery_id)).where(
                        CommunicationDelivery.event_id.in_(event_ids)
                    )
                )
            )
            or 0
        )
        if total > MAX_RECONCILIATION_DELIVERIES:
            return [], total, True
        query = (
            select(CommunicationDelivery)
            .where(CommunicationDelivery.event_id.in_(event_ids))
            .order_by(
                CommunicationDelivery.event_id.asc(),
                CommunicationDelivery.delivery_id.asc(),
            )
            .limit(MAX_RECONCILIATION_DELIVERIES + 1)
        )
        if lock:
            query = query.with_for_update(skip_locked=True)
        deliveries = list((await session.execute(query)).scalars())
        overflow = len(deliveries) > MAX_RECONCILIATION_DELIVERIES
        return (
            deliveries[:MAX_RECONCILIATION_DELIVERIES],
            max(total, len(deliveries)),
            overflow,
        )

    @staticmethod
    async def _load_attempts(
        session: AsyncSession,
        delivery_ids: tuple[str, ...],
        *,
        lock: bool,
    ) -> tuple[list[CommunicationDeliveryAttempt], int, bool]:
        if not delivery_ids:
            return [], 0, False
        total = int(
            (
                await session.scalar(
                    select(func.count(CommunicationDeliveryAttempt.delivery_id)).where(
                        CommunicationDeliveryAttempt.delivery_id.in_(delivery_ids)
                    )
                )
            )
            or 0
        )
        if total > MAX_RECONCILIATION_ATTEMPTS:
            return [], total, True
        query = (
            select(CommunicationDeliveryAttempt)
            .where(
                CommunicationDeliveryAttempt.delivery_id.in_(delivery_ids)
            )
            .limit(MAX_RECONCILIATION_ATTEMPTS + 1)
        )
        if lock:
            query = query.with_for_update(skip_locked=True)
        attempts = list((await session.execute(query)).scalars())
        overflow = len(attempts) > MAX_RECONCILIATION_ATTEMPTS
        return (
            attempts[:MAX_RECONCILIATION_ATTEMPTS],
            max(total, len(attempts)),
            overflow,
        )

    @staticmethod
    def _has_ownership(item: Any) -> bool:
        return any(
            value is not None
            for value in (
                getattr(item, "worker_id", None),
                getattr(item, "lease_token", None),
                getattr(item, "lease_expires_at", None),
            )
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        # SQLite drops timezone metadata even for timezone-aware columns.
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    async def _assert_execution_preflight(
        cls,
        session: AsyncSession,
        *,
        runtime_lock: RuntimeLock | None,
        app_role: str | None,
    ) -> CommunicationRuntimeConfig:
        config = CommunicationRuntimeConfig.from_settings()
        if config.channel != cls.CHANNEL:
            raise InstallationEstimateBacklogExecutionBlocked(
                "communications_runtime_channel_invalid"
            )
        if config.enabled or config.allow_all_mode:
            raise InstallationEstimateBacklogExecutionBlocked(
                "communications_runtime_deployment_gate_enabled"
            )
        if (
            runtime_lock is None
            or runtime_lock.name != config.lock_name
            or runtime_lock.connection is None
            or not runtime_lock.acquired
            or not await runtime_lock.is_held()
        ):
            raise InstallationEstimateBacklogExecutionBlocked(
                "communications_runtime_lock_required"
            )
        try:
            await CommunicationsTelegramCanary.preflight_control(
                session,
                app_role=app_role,
            )
        except CommunicationsCanarySafetyError as error:
            raise InstallationEstimateBacklogExecutionBlocked(
                error.error_code
            ) from None

        await CommunicationRuntimeStateService.ensure_state(
            session,
            channel=cls.CHANNEL,
        )
        state = await session.get(
            CommunicationRuntimeState,
            cls.CHANNEL,
            populate_existing=True,
            with_for_update=True,
        )
        if state is None:  # pragma: no cover - ensured immediately above
            raise InstallationEstimateBacklogExecutionBlocked(
                "communications_runtime_state_missing"
            )
        if CommunicationRuntimeMode(state.mode) != CommunicationRuntimeMode.OFF:
            raise InstallationEstimateBacklogExecutionBlocked(
                "communications_runtime_mode_not_off"
            )
        # The advisory lock is the definitive live-ownership fence. Requiring
        # STOPPED as well prevents reconciliation while a dormant worker is
        # still cycling in DISABLED state and documents the operator contract.
        if (
            CommunicationRuntimeStatus(state.status)
            != CommunicationRuntimeStatus.STOPPED
        ):
            raise InstallationEstimateBacklogExecutionBlocked(
                "communications_runtime_not_stopped"
            )
        return config

    @classmethod
    def _validate_candidate_set(
        cls,
        *,
        candidates: list[IntegrationOutboxEvent],
        deliveries: list[CommunicationDelivery],
        delivery_total: int,
        attempts: list[CommunicationDeliveryAttempt],
        attempt_total: int,
    ) -> tuple[
        list[IntegrationOutboxEvent],
        list[CommunicationDelivery],
        dict[tuple[str, int], CommunicationDeliveryAttempt],
        int,
        int,
    ]:
        delivery_conflicts = 0
        ownership_conflicts = sum(
            1 for event in candidates if cls._has_ownership(event)
        )
        if len(deliveries) != delivery_total or len(attempts) != attempt_total:
            # A related row was skipped because another transaction owns it.
            ownership_conflicts += 1

        attempts_by_key = {
            (attempt.delivery_id, int(attempt.attempt_no)): attempt
            for attempt in attempts
        }
        attempts_by_delivery: dict[str, list[CommunicationDeliveryAttempt]] = {}
        for attempt in attempts:
            attempts_by_delivery.setdefault(attempt.delivery_id, []).append(
                attempt
            )
        nonterminal = [
            delivery
            for delivery in deliveries
            if delivery.status in NON_TERMINAL_DELIVERY_STATUSES
        ]
        for delivery in deliveries:
            if (
                delivery.channel != cls.CHANNEL
                or delivery.template_key != cls.TEMPLATE_KEY
                or delivery.template_version != 1
            ):
                delivery_conflicts += 1
        for delivery in nonterminal:
            attempts_count = int(delivery.attempts)
            max_attempts = int(delivery.max_attempts)
            delivery_attempts = sorted(
                attempts_by_delivery.get(delivery.delivery_id, []),
                key=lambda attempt: int(attempt.attempt_no),
            )
            actual_attempt_numbers = [
                int(attempt.attempt_no) for attempt in delivery_attempts
            ]
            if (
                attempts_count > MAX_RECONCILIATION_ATTEMPTS
                or len(actual_attempt_numbers) != attempts_count
                or any(
                    attempt_no != expected_attempt_no
                    for expected_attempt_no, attempt_no in enumerate(
                        actual_attempt_numbers,
                        start=1,
                    )
                )
            ):
                delivery_conflicts += 1
                continue
            if delivery.status == "running":
                current = attempts_by_key.get(
                    (delivery.delivery_id, attempts_count)
                )
                if (
                    not cls._has_ownership(delivery)
                    or attempts_count < 1
                    or current is None
                    or current.outcome != "running"
                    or current.finished_at is not None
                    or any(
                        attempt.outcome != "retry"
                        or attempt.finished_at is None
                        for attempt in delivery_attempts[:-1]
                    )
                ):
                    delivery_conflicts += 1
            else:
                if cls._has_ownership(delivery):
                    ownership_conflicts += 1
                if delivery.status == "queued" and (
                    attempts_count != 0 or delivery_attempts
                ):
                    delivery_conflicts += 1
                current = attempts_by_key.get(
                    (delivery.delivery_id, attempts_count)
                )
                if (
                    delivery.status == "retry"
                    and (
                        attempts_count < 1
                        or attempts_count >= max_attempts
                        or current is None
                        or current.outcome != "retry"
                        or current.finished_at is None
                        or any(
                            attempt.outcome != "retry"
                            or attempt.finished_at is None
                            for attempt in delivery_attempts[:-1]
                        )
                    )
                ):
                    delivery_conflicts += 1

        safe_events = (
            candidates
            if delivery_conflicts == 0 and ownership_conflicts == 0
            else []
        )
        return (
            safe_events,
            nonterminal,
            attempts_by_key,
            delivery_conflicts,
            ownership_conflicts,
        )

    @classmethod
    def _suppress_delivery(
        cls,
        session: AsyncSession,
        *,
        delivery: CommunicationDelivery,
        attempts_by_key: dict[
            tuple[str, int],
            CommunicationDeliveryAttempt,
        ],
        now: datetime,
    ) -> bool:
        if delivery.status == "running":
            attempt = attempts_by_key[
                (delivery.delivery_id, int(delivery.attempts))
            ]
            attempt.outcome = "dead"
            attempt.finished_at = now
            attempt.error_category = STALE_BACKLOG_ERROR_CATEGORY
            attempt.error_code = STALE_BACKLOG_ERROR_CODE
            attempt.retry_after_seconds = None
            attempt.provider_latency_ms = None
            # A running attempt may have crossed the Telegram boundary before
            # the stopped runtime lost ownership. Preserve that uncertainty.
            attempt.ambiguous = True
            session.add(attempt)
            terminal_status = "dead"
            ambiguous = True
        else:
            delivery.attempts = int(delivery.attempts) + 1
            attempt = CommunicationDeliveryAttempt(
                delivery_id=delivery.delivery_id,
                attempt_no=int(delivery.attempts),
                started_at=now,
                finished_at=now,
                outcome="canceled",
                error_category=STALE_BACKLOG_ERROR_CATEGORY,
                error_code=STALE_BACKLOG_ERROR_CODE,
                ambiguous=False,
            )
            session.add(attempt)
            terminal_status = "canceled"
            ambiguous = False

        delivery.status = terminal_status
        delivery.worker_id = None
        delivery.lease_token = None
        delivery.lease_expires_at = None
        delivery.provider_message_id = None
        delivery.last_error_category = STALE_BACKLOG_ERROR_CATEGORY
        delivery.last_error_code = STALE_BACKLOG_ERROR_CODE
        delivery.last_error_message = STALE_BACKLOG_ERROR_MESSAGE
        delivery.sent_at = None
        delivery.finished_at = now
        delivery.updated_at = now
        session.add(delivery)
        return ambiguous

    @classmethod
    async def reconcile(
        cls,
        session: AsyncSession,
        *,
        cutoff: datetime,
        limit: int,
        execute: bool = False,
        now: datetime | None = None,
        runtime_lock: RuntimeLock | None = None,
        app_role: str | None = None,
    ) -> InstallationEstimateBacklogReport:
        reconciliation_time = now or datetime.now(timezone.utc)
        if (
            reconciliation_time.tzinfo is None
            or reconciliation_time.utcoffset() is None
        ):
            raise ValueError("now must include a timezone")
        reconciliation_time = reconciliation_time.astimezone(timezone.utc)
        normalized_cutoff = cls._normalize_cutoff(
            cutoff,
            now=reconciliation_time,
        )
        normalized_limit = cls._validate_limit(limit)

        if execute:
            await cls._assert_execution_preflight(
                session,
                runtime_lock=runtime_lock,
                app_role=app_role,
            )

        candidate_total = await cls._candidate_total(
            session,
            cutoff=normalized_cutoff,
        )
        candidates = await cls._select_candidates(
            session,
            cutoff=normalized_cutoff,
            limit=normalized_limit,
            lock=execute,
        )
        pending_candidate_count = sum(
            1 for event in candidates if event.status == "pending"
        )
        materialized_candidate_count = sum(
            1 for event in candidates if event.status in {"processing", "published"}
        )
        event_ids = tuple(event.event_id for event in candidates)
        (
            deliveries,
            delivery_total,
            delivery_inventory_overflow,
        ) = await cls._load_deliveries(
            session,
            event_ids,
            lock=execute,
        )
        delivery_ids = tuple(delivery.delivery_id for delivery in deliveries)
        attempts: list[CommunicationDeliveryAttempt] = []
        attempt_total = 0
        attempt_inventory_overflow = False
        if not delivery_inventory_overflow:
            (
                attempts,
                attempt_total,
                attempt_inventory_overflow,
            ) = await cls._load_attempts(
                session,
                delivery_ids,
                lock=execute,
            )
        inventory_overflow_count = int(delivery_inventory_overflow) + int(
            attempt_inventory_overflow
        )
        if inventory_overflow_count:
            safe_candidates: list[IntegrationOutboxEvent] = []
            nonterminal_deliveries: list[CommunicationDelivery] = []
            attempts_by_key: dict[
                tuple[str, int], CommunicationDeliveryAttempt
            ] = {}
            delivery_conflict_count = 0
            ownership_conflict_count = 0
        else:
            (
                safe_candidates,
                nonterminal_deliveries,
                attempts_by_key,
                delivery_conflict_count,
                ownership_conflict_count,
            ) = cls._validate_candidate_set(
                candidates=candidates,
                deliveries=deliveries,
                delivery_total=delivery_total,
                attempts=attempts,
                attempt_total=attempt_total,
            )
        if execute and inventory_overflow_count:
            raise InstallationEstimateBacklogExecutionBlocked(
                "stale_backlog_batch_too_large"
            )
        if execute and (
            delivery_conflict_count > 0 or ownership_conflict_count > 0
        ):
            raise InstallationEstimateBacklogExecutionBlocked(
                "stale_backlog_conflict"
            )

        suppressed_delivery_count = 0
        ambiguous_delivery_count = 0
        if execute:
            for delivery in nonterminal_deliveries:
                ambiguous_delivery_count += int(
                    cls._suppress_delivery(
                        session,
                        delivery=delivery,
                        attempts_by_key=attempts_by_key,
                        now=reconciliation_time,
                    )
                )
                suppressed_delivery_count += 1
            for event in safe_candidates:
                if (
                    event.event_type != cls.EVENT_TYPE
                    or event.status not in {"pending", "processing", "published"}
                    or cls._as_utc(event.created_at) >= normalized_cutoff
                ):
                    raise InstallationEstimateBacklogExecutionBlocked(
                        "stale_backlog_candidate_changed"
                    )
                event.status = "dead"
                event.worker_id = None
                event.lease_token = None
                event.lease_expires_at = None
                event.last_error_code = STALE_BACKLOG_ERROR_CODE
                event.last_error_message = STALE_BACKLOG_ERROR_MESSAGE
                event.updated_at = reconciliation_time
                session.add(event)
            await session.flush()

        remaining_candidate_count = (
            await cls._candidate_total(session, cutoff=normalized_cutoff)
            if execute
            else candidate_total
        )
        return InstallationEstimateBacklogReport(
            mode="execute" if execute else "dry_run",
            event_type=cls.EVENT_TYPE,
            cutoff=normalized_cutoff.isoformat(),
            limit=normalized_limit,
            candidate_total=candidate_total,
            selected_count=len(candidates),
            pending_candidate_count=pending_candidate_count,
            materialized_candidate_count=materialized_candidate_count,
            nonterminal_delivery_count=len(nonterminal_deliveries),
            would_suppress_count=len(safe_candidates),
            suppressed_count=len(safe_candidates) if execute else 0,
            suppressed_delivery_count=suppressed_delivery_count,
            ambiguous_delivery_count=ambiguous_delivery_count,
            delivery_conflict_count=delivery_conflict_count,
            ownership_conflict_count=ownership_conflict_count,
            inventory_overflow_count=inventory_overflow_count,
            remaining_candidate_count=remaining_candidate_count,
            truncated=candidate_total > len(candidates),
            activation_safe=(
                remaining_candidate_count == 0
                and delivery_conflict_count == 0
                and ownership_conflict_count == 0
                and inventory_overflow_count == 0
            ),
        )
