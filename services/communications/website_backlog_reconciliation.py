"""All-or-nothing manifest reconciliation for the website event allowlist."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    CommunicationDelivery,
    CommunicationDeliveryAttempt,
    IntegrationOutboxEvent,
)
from services.communications.backlog_reconciliation import (
    InstallationEstimateBacklogExecutionBlocked,
    InstallationEstimateBacklogReconciliation,
)
from services.communications.backlog_reconciliation_contracts import (
    MAX_RECONCILIATION_ATTEMPTS,
    MAX_RECONCILIATION_DELIVERIES,
    MAX_RECONCILIATION_LIMIT,
    STALE_BACKLOG_ERROR_CODE,
)
from services.communications.tenant_website_events import (
    TENANT_WEBSITE_EVENT_TEMPLATE_KEYS,
    TENANT_WEBSITE_EVENT_TYPES,
)
from services.runtime_lock_service import RuntimeLock


BacklogDisposition = Literal["retain", "terminal_no_send"]


@dataclass(frozen=True)
class WebsiteBacklogManifestItem:
    event_type: str
    cutoff: datetime
    expected_count: int
    disposition: BacklogDisposition

    def __post_init__(self) -> None:
        if self.event_type not in TENANT_WEBSITE_EVENT_TEMPLATE_KEYS:
            raise ValueError("Website backlog event type is not allowlisted")
        if self.cutoff.tzinfo is None or self.cutoff.utcoffset() is None:
            raise ValueError("Website backlog cutoff must include a timezone")
        if (
            isinstance(self.expected_count, bool)
            or not isinstance(self.expected_count, int)
            or not 0 <= self.expected_count <= MAX_RECONCILIATION_LIMIT
        ):
            raise ValueError(
                "Website backlog expected count is outside the safe bound"
            )
        if self.disposition not in {"retain", "terminal_no_send"}:
            raise ValueError("Website backlog disposition is invalid")


@dataclass(frozen=True)
class WebsiteBacklogTypeReport:
    event_type: str
    cutoff: str
    expected_count: int
    disposition: BacklogDisposition
    candidate_count: int
    selected_count: int
    nonterminal_delivery_count: int
    ambiguous_delivery_count: int
    conflict_count: int
    inventory_overflow_count: int
    terminalized_count: int
    terminalized_delivery_count: int
    remaining_candidate_count: int
    activation_blocked: bool


@dataclass(frozen=True)
class WebsiteBacklogManifestReport:
    mode: Literal["dry_run", "execute"]
    operation_id: str
    event_types: tuple[WebsiteBacklogTypeReport, ...]
    activation_safe: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "operation_id": self.operation_id,
            "event_types": [asdict(item) for item in self.event_types],
            "activation_safe": self.activation_safe,
        }


@dataclass
class _Inventory:
    item: WebsiteBacklogManifestItem
    reconciler: type[InstallationEstimateBacklogReconciliation]
    candidates: list[IntegrationOutboxEvent]
    nonterminal_deliveries: list[CommunicationDelivery]
    attempts_by_key: dict[tuple[str, int], CommunicationDeliveryAttempt]
    candidate_count: int
    ambiguous_delivery_count: int
    conflict_count: int
    overflow_count: int


class WebsiteCommunicationBacklogReconciliation:
    """Reconcile one declared disposition for every reviewed website event."""

    @staticmethod
    def normalize_operation_id(operation_id: str) -> str:
        try:
            parsed = uuid.UUID(str(operation_id or "").strip())
        except (AttributeError, TypeError, ValueError):
            raise ValueError("Website backlog operation ID must be a UUID") from None
        return str(parsed)

    @staticmethod
    def _typed_reconciler(
        item: WebsiteBacklogManifestItem,
    ) -> type[InstallationEstimateBacklogReconciliation]:
        return type(
            "TypedWebsiteBacklogReconciliation",
            (InstallationEstimateBacklogReconciliation,),
            {
                "EVENT_TYPE": item.event_type,
                "TEMPLATE_KEY": TENANT_WEBSITE_EVENT_TEMPLATE_KEYS[
                    item.event_type
                ],
            },
        )

    @staticmethod
    def _validate_manifest(
        manifest: tuple[WebsiteBacklogManifestItem, ...],
        *,
        execute: bool,
    ) -> tuple[WebsiteBacklogManifestItem, ...]:
        if not manifest:
            raise ValueError("Website backlog manifest cannot be empty")
        by_type = {item.event_type: item for item in manifest}
        if len(by_type) != len(manifest):
            raise ValueError("Website backlog manifest event types must be unique")
        if execute and set(by_type) != set(TENANT_WEBSITE_EVENT_TYPES):
            raise InstallationEstimateBacklogExecutionBlocked(
                "website_backlog_manifest_must_cover_allowlist"
            )
        return tuple(
            by_type[event_type]
            for event_type in TENANT_WEBSITE_EVENT_TYPES
            if event_type in by_type
        )

    @classmethod
    async def _inventory(
        cls,
        session: AsyncSession,
        *,
        item: WebsiteBacklogManifestItem,
        lock: bool,
        now: datetime,
    ) -> _Inventory:
        reconciler = cls._typed_reconciler(item)
        cutoff = reconciler._normalize_cutoff(item.cutoff, now=now)
        candidate_count = await reconciler._candidate_total(
            session,
            cutoff=cutoff,
        )
        candidates = await reconciler._select_candidates(
            session,
            cutoff=cutoff,
            limit=max(1, item.expected_count),
            lock=lock,
        )
        event_ids = tuple(event.event_id for event in candidates)
        deliveries, delivery_total, delivery_overflow = (
            await reconciler._load_deliveries(
                session,
                event_ids,
                lock=lock,
            )
        )
        attempts: list[CommunicationDeliveryAttempt] = []
        attempt_total = 0
        attempt_overflow = False
        if not delivery_overflow:
            attempts, attempt_total, attempt_overflow = (
                await reconciler._load_attempts(
                    session,
                    tuple(delivery.delivery_id for delivery in deliveries),
                    lock=lock,
                )
            )
        overflow_count = int(delivery_overflow) + int(attempt_overflow)
        if overflow_count:
            nonterminal_deliveries: list[CommunicationDelivery] = []
            attempts_by_key: dict[
                tuple[str, int], CommunicationDeliveryAttempt
            ] = {}
            conflict_count = 0
        else:
            (
                safe_candidates,
                nonterminal_deliveries,
                attempts_by_key,
                delivery_conflicts,
                ownership_conflicts,
            ) = reconciler._validate_candidate_set(
                candidates=candidates,
                deliveries=deliveries,
                delivery_total=delivery_total,
                attempts=attempts,
                attempt_total=attempt_total,
            )
            conflict_count = delivery_conflicts + ownership_conflicts
            if len(safe_candidates) != len(candidates):
                conflict_count = max(1, conflict_count)
        ambiguous_delivery_ids = {
            attempt.delivery_id for attempt in attempts if attempt.ambiguous
        }
        return _Inventory(
            item=WebsiteBacklogManifestItem(
                event_type=item.event_type,
                cutoff=cutoff,
                expected_count=item.expected_count,
                disposition=item.disposition,
            ),
            reconciler=reconciler,
            candidates=candidates,
            nonterminal_deliveries=nonterminal_deliveries,
            attempts_by_key=attempts_by_key,
            candidate_count=candidate_count,
            ambiguous_delivery_count=len(ambiguous_delivery_ids),
            conflict_count=conflict_count,
            overflow_count=overflow_count,
        )

    @staticmethod
    def _assert_inventory(inventory: _Inventory) -> None:
        if inventory.candidate_count != inventory.item.expected_count:
            raise InstallationEstimateBacklogExecutionBlocked(
                "website_backlog_expected_count_changed"
            )
        if len(inventory.candidates) != inventory.candidate_count:
            raise InstallationEstimateBacklogExecutionBlocked(
                "website_backlog_candidate_lock_conflict"
            )
        if inventory.overflow_count:
            raise InstallationEstimateBacklogExecutionBlocked(
                "website_backlog_inventory_too_large"
            )
        if inventory.conflict_count:
            raise InstallationEstimateBacklogExecutionBlocked(
                "website_backlog_inventory_conflict"
            )

    @classmethod
    async def reconcile_manifest(
        cls,
        session: AsyncSession,
        *,
        manifest: tuple[WebsiteBacklogManifestItem, ...],
        operation_id: str,
        execute: bool = False,
        now: datetime | None = None,
        runtime_lock: RuntimeLock | None = None,
        app_role: str | None = None,
    ) -> WebsiteBacklogManifestReport:
        normalized_operation_id = cls.normalize_operation_id(operation_id)
        ordered_manifest = cls._validate_manifest(manifest, execute=execute)
        reconciliation_time = now or datetime.now(timezone.utc)
        if (
            reconciliation_time.tzinfo is None
            or reconciliation_time.utcoffset() is None
        ):
            raise ValueError("now must include a timezone")
        reconciliation_time = reconciliation_time.astimezone(timezone.utc)

        if execute:
            await InstallationEstimateBacklogReconciliation._assert_execution_preflight(
                session,
                runtime_lock=runtime_lock,
                app_role=app_role,
            )
        inventories = [
            await cls._inventory(
                session,
                item=item,
                lock=execute,
                now=reconciliation_time,
            )
            for item in ordered_manifest
        ]
        if execute:
            total_deliveries = sum(
                len(item.nonterminal_deliveries) for item in inventories
            )
            total_attempts = sum(
                len(item.attempts_by_key) for item in inventories
            )
            if (
                total_deliveries > MAX_RECONCILIATION_DELIVERIES
                or total_attempts > MAX_RECONCILIATION_ATTEMPTS
            ):
                raise InstallationEstimateBacklogExecutionBlocked(
                    "website_backlog_manifest_too_large"
                )
            for inventory in inventories:
                cls._assert_inventory(inventory)

        terminalized: dict[str, tuple[int, int]] = {}
        if execute:
            audit_message = (
                "Terminal no-send website backlog reconciliation operation "
                f"{normalized_operation_id}"
            )
            for inventory in inventories:
                if inventory.item.disposition == "retain":
                    terminalized[inventory.item.event_type] = (0, 0)
                    continue
                for delivery in inventory.nonterminal_deliveries:
                    inventory.reconciler._suppress_delivery(
                        session,
                        delivery=delivery,
                        attempts_by_key=inventory.attempts_by_key,
                        now=reconciliation_time,
                    )
                    delivery.last_error_message = audit_message
                for event in inventory.candidates:
                    event.status = "dead"
                    event.worker_id = None
                    event.lease_token = None
                    event.lease_expires_at = None
                    event.last_error_code = STALE_BACKLOG_ERROR_CODE
                    event.last_error_message = audit_message
                    event.updated_at = reconciliation_time
                    session.add(event)
                terminalized[inventory.item.event_type] = (
                    len(inventory.candidates),
                    len(inventory.nonterminal_deliveries),
                )
            await session.flush()

        reports: list[WebsiteBacklogTypeReport] = []
        for inventory in inventories:
            remaining = await inventory.reconciler._candidate_total(
                session,
                cutoff=inventory.item.cutoff,
            )
            count_mismatch = (
                inventory.candidate_count != inventory.item.expected_count
                or len(inventory.candidates) != inventory.candidate_count
            )
            terminalized_count, terminalized_deliveries = terminalized.get(
                inventory.item.event_type,
                (0, 0),
            )
            reports.append(
                WebsiteBacklogTypeReport(
                    event_type=inventory.item.event_type,
                    cutoff=inventory.item.cutoff.isoformat(),
                    expected_count=inventory.item.expected_count,
                    disposition=inventory.item.disposition,
                    candidate_count=inventory.candidate_count,
                    selected_count=len(inventory.candidates),
                    nonterminal_delivery_count=len(
                        inventory.nonterminal_deliveries
                    ),
                    ambiguous_delivery_count=(
                        inventory.ambiguous_delivery_count
                    ),
                    conflict_count=inventory.conflict_count + int(count_mismatch),
                    inventory_overflow_count=inventory.overflow_count,
                    terminalized_count=terminalized_count,
                    terminalized_delivery_count=terminalized_deliveries,
                    remaining_candidate_count=remaining,
                    activation_blocked=(
                        inventory.item.disposition == "retain"
                        or remaining > 0
                        or inventory.conflict_count > 0
                        or inventory.overflow_count > 0
                        or count_mismatch
                    ),
                )
            )
        return WebsiteBacklogManifestReport(
            mode="execute" if execute else "dry_run",
            operation_id=normalized_operation_id,
            event_types=tuple(reports),
            activation_safe=bool(reports)
            and all(not report.activation_blocked for report in reports)
            and {report.event_type for report in reports}
            == set(TENANT_WEBSITE_EVENT_TYPES),
        )
