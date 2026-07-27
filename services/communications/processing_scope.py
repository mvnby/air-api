from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from services.communications.canary_run_id import normalize_canary_run_id
from services.communications.template_registry import (
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
    INSTALLATION_ESTIMATE_TEMPLATE_KEY,
    TELEGRAM_CANARY_REQUESTED_EVENT,
    TELEGRAM_CANARY_TEMPLATE_KEY,
    telegram_canary_event_id,
)
from services.communications.staff_task_contracts import (
    STAFF_TASK_EVENT_TYPE_VALUES,
    STAFF_TASK_TEMPLATE_KEY_VALUES,
)


ProcessingMode = Literal["canary", "all", "staff_bot"]
CANARY_EVENT_TYPES = (TELEGRAM_CANARY_REQUESTED_EVENT,)
CANARY_TEMPLATE_KEYS = (TELEGRAM_CANARY_TEMPLATE_KEY,)
# "all" is the production website rollout scope, not a synonym for every
# registered communication. Keep it deliberately narrow and expand it only
# through a separately reviewed rollout.
ALL_EVENT_TYPES = (INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,)
ALL_TEMPLATE_KEYS = (INSTALLATION_ESTIMATE_TEMPLATE_KEY,)
STAFF_BOT_EVENT_TYPES = STAFF_TASK_EVENT_TYPE_VALUES
STAFF_BOT_TEMPLATE_KEYS = STAFF_TASK_TEMPLATE_KEY_VALUES


@dataclass(frozen=True)
class CommunicationProcessingScope:
    """Explicit allowlist for one immutable runtime control revision."""

    mode: ProcessingMode
    control_revision: int
    outbox_event_types: tuple[str, ...]
    delivery_template_keys: tuple[str, ...]
    exact_event_id: str | None = None
    canary_run_id: str | None = None
    event_created_at_watermark: datetime | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"canary", "all", "staff_bot"}:
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
            if (
                self.canary_run_id is None
                or self.exact_event_id is None
                or self.event_created_at_watermark is not None
            ):
                raise ValueError("Canary processing scope requires an exact run")
            normalized_run_id = normalize_canary_run_id(self.canary_run_id)
            if (
                normalized_run_id != self.canary_run_id
                or self.outbox_event_types != CANARY_EVENT_TYPES
                or self.delivery_template_keys != CANARY_TEMPLATE_KEYS
                or self.exact_event_id != telegram_canary_event_id(normalized_run_id)
            ):
                raise ValueError("Canary processing scope identity is inconsistent")
        elif self.mode == "staff_bot":
            if (
                self.canary_run_id is not None
                or self.exact_event_id is not None
                or self.event_created_at_watermark is not None
                or self.outbox_event_types != STAFF_BOT_EVENT_TYPES
                or self.delivery_template_keys != STAFF_BOT_TEMPLATE_KEYS
            ):
                raise ValueError("Staff bot processing scope allowlist is inconsistent")
        else:
            watermark = self.event_created_at_watermark
            if (
                self.canary_run_id is not None
                or self.exact_event_id is not None
                or self.outbox_event_types != ALL_EVENT_TYPES
                or self.delivery_template_keys != ALL_TEMPLATE_KEYS
                or watermark is None
                or watermark.tzinfo is None
                or watermark.utcoffset() is None
            ):
                raise ValueError("Full processing scope allowlist is inconsistent")
            if watermark.utcoffset() != timedelta(0):
                raise ValueError("Full processing watermark must be normalized to UTC")

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
    def all(
        cls,
        *,
        control_revision: int,
        event_created_at_watermark: datetime,
    ) -> "CommunicationProcessingScope":
        # Keep this list explicit: adding a renderer must never widen runtime
        # delivery without a separately reviewed rollout change.
        return cls(
            mode="all",
            control_revision=control_revision,
            outbox_event_types=ALL_EVENT_TYPES,
            delivery_template_keys=ALL_TEMPLATE_KEYS,
            event_created_at_watermark=event_created_at_watermark,
        )

    @classmethod
    def staff_bot(cls, *, control_revision: int = 1) -> "CommunicationProcessingScope":
        return cls(
            mode="staff_bot",
            control_revision=control_revision,
            outbox_event_types=STAFF_BOT_EVENT_TYPES,
            delivery_template_keys=STAFF_BOT_TEMPLATE_KEYS,
        )

    def matches_control(
        self,
        *,
        mode: str,
        canary_run_id: str | None,
        control_revision: int,
        event_created_at_watermark: datetime | None = None,
    ) -> bool:
        return (
            self.mode == mode
            and self.canary_run_id == canary_run_id
            and self.control_revision == int(control_revision)
            and (
                self.mode != "all"
                or self.event_created_at_watermark == event_created_at_watermark
            )
        )
