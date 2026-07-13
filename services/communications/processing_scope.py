from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from services.communications.canary_run_id import normalize_canary_run_id
from services.communications.template_registry import (
    CONTACT_LEAD_TEMPLATE_KEY,
    ORDER_TEMPLATE_KEY,
    PUBLIC_CONTACT_LEAD_CREATED_EVENT,
    PUBLIC_ORDER_CREATED_EVENT,
    TELEGRAM_CANARY_REQUESTED_EVENT,
    TELEGRAM_CANARY_TEMPLATE_KEY,
    telegram_canary_event_id,
)


ProcessingMode = Literal["canary", "all"]
CANARY_EVENT_TYPES = (TELEGRAM_CANARY_REQUESTED_EVENT,)
CANARY_TEMPLATE_KEYS = (TELEGRAM_CANARY_TEMPLATE_KEY,)
ALL_EVENT_TYPES = (
    PUBLIC_ORDER_CREATED_EVENT,
    PUBLIC_CONTACT_LEAD_CREATED_EVENT,
    TELEGRAM_CANARY_REQUESTED_EVENT,
)
ALL_TEMPLATE_KEYS = (
    ORDER_TEMPLATE_KEY,
    CONTACT_LEAD_TEMPLATE_KEY,
    TELEGRAM_CANARY_TEMPLATE_KEY,
)


@dataclass(frozen=True)
class CommunicationProcessingScope:
    """Explicit allowlist for one immutable runtime control revision."""

    mode: ProcessingMode
    control_revision: int
    outbox_event_types: tuple[str, ...]
    delivery_template_keys: tuple[str, ...]
    exact_event_id: str | None = None
    canary_run_id: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"canary", "all"}:
            raise ValueError("Communication processing mode is invalid")
        if type(self.control_revision) is not int or self.control_revision < 0:
            raise ValueError(
                "Communication control revision must be a non-negative integer"
            )
        if not self.outbox_event_types or not self.delivery_template_keys:
            raise ValueError("Communication processing scope cannot be empty")
        if len(set(self.outbox_event_types)) != len(self.outbox_event_types):
            raise ValueError("Communication event scope contains duplicates")
        if len(set(self.delivery_template_keys)) != len(self.delivery_template_keys):
            raise ValueError("Communication template scope contains duplicates")
        if self.mode == "canary":
            if self.canary_run_id is None or self.exact_event_id is None:
                raise ValueError("Canary processing scope requires an exact run")
            normalized_run_id = normalize_canary_run_id(self.canary_run_id)
            if (
                normalized_run_id != self.canary_run_id
                or self.outbox_event_types != CANARY_EVENT_TYPES
                or self.delivery_template_keys != CANARY_TEMPLATE_KEYS
                or self.exact_event_id != telegram_canary_event_id(normalized_run_id)
            ):
                raise ValueError("Canary processing scope identity is inconsistent")
        elif (
            self.canary_run_id is not None
            or self.exact_event_id is not None
            or self.outbox_event_types != ALL_EVENT_TYPES
            or self.delivery_template_keys != ALL_TEMPLATE_KEYS
        ):
            raise ValueError("Full processing scope allowlist is inconsistent")

    @classmethod
    def canary(
        cls,
        *,
        run_id: str,
        control_revision: int,
    ) -> "CommunicationProcessingScope":
        normalized_run_id = normalize_canary_run_id(run_id)
        return cls(
            mode="canary",
            control_revision=control_revision,
            outbox_event_types=CANARY_EVENT_TYPES,
            delivery_template_keys=CANARY_TEMPLATE_KEYS,
            exact_event_id=telegram_canary_event_id(normalized_run_id),
            canary_run_id=normalized_run_id,
        )

    @classmethod
    def all(cls, *, control_revision: int) -> "CommunicationProcessingScope":
        # Keep this list explicit: adding a renderer must never widen runtime
        # delivery without a separately reviewed rollout change.
        return cls(
            mode="all",
            control_revision=control_revision,
            outbox_event_types=ALL_EVENT_TYPES,
            delivery_template_keys=ALL_TEMPLATE_KEYS,
        )

    def matches_control(
        self,
        *,
        mode: str,
        canary_run_id: str | None,
        control_revision: int,
    ) -> bool:
        return (
            self.mode == mode
            and self.canary_run_id == canary_run_id
            and self.control_revision == int(control_revision)
        )
