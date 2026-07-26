"""Privacy-safe contracts and hard bounds for backlog reconciliation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


STALE_BACKLOG_ERROR_CODE = "stale_backlog_suppressed"
STALE_BACKLOG_ERROR_MESSAGE = (
    "Suppressed by explicit stale installation-estimate backlog reconciliation"
)
STALE_BACKLOG_ERROR_CATEGORY = "policy"
MAX_RECONCILIATION_LIMIT = 1_000
MAX_RECONCILIATION_DELIVERIES = 5_000
MAX_RECONCILIATION_ATTEMPTS = 40_000
NON_TERMINAL_DELIVERY_STATUSES = frozenset({"queued", "retry", "running"})


class InstallationEstimateBacklogExecutionBlocked(RuntimeError):
    """Privacy-safe, operator-actionable execution rejection."""

    def __init__(self, error_code: str) -> None:
        self.error_code = str(error_code)
        super().__init__(self.error_code)


@dataclass(frozen=True)
class InstallationEstimateBacklogReport:
    """Privacy-safe summary without event, recipient, or customer identifiers."""

    mode: str
    event_type: str
    cutoff: str
    limit: int
    candidate_total: int
    selected_count: int
    pending_candidate_count: int
    materialized_candidate_count: int
    nonterminal_delivery_count: int
    would_suppress_count: int
    suppressed_count: int
    suppressed_delivery_count: int
    ambiguous_delivery_count: int
    delivery_conflict_count: int
    ownership_conflict_count: int
    inventory_overflow_count: int
    remaining_candidate_count: int
    truncated: bool
    activation_safe: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
