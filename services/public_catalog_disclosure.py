"""Disclosure policy for canonical and white-label public catalog payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_PUBLIC_AVAILABILITY_STATUSES = frozenset(
    {
        "in_stock_now",
        "available_2_3_days",
        "check_availability",
        "out_of_stock",
    }
)


@dataclass(frozen=True)
class PublicAvailabilityPayload:
    vitebsk_qty: int
    minsk_qty: int
    availability_status: str | None
    public_stock_state: str | None
    delivery_min_days: int | None
    delivery_max_days: int | None


@dataclass(frozen=True)
class PublicCatalogDisclosurePolicy:
    """Controls fields that reveal MVN inventory topology or source provenance."""

    expose_legacy_availability: bool
    expose_source_provenance: bool

    def project_availability(
        self,
        supply_metrics: dict[str, Any] | None,
    ) -> PublicAvailabilityPayload:
        metrics = supply_metrics or {}
        raw_status = metrics.get("availability_status")
        availability_status = str(raw_status) if raw_status is not None else None
        if (
            not self.expose_legacy_availability
            and availability_status not in _PUBLIC_AVAILABILITY_STATUSES
        ):
            availability_status = "out_of_stock"
        public_stock_state, delivery_min_days, delivery_max_days = (
            resolve_public_stock_state(availability_status)
        )
        return PublicAvailabilityPayload(
            vitebsk_qty=(
                int(metrics.get("vitebsk_qty", 0) or 0)
                if self.expose_legacy_availability
                else 0
            ),
            minsk_qty=(
                int(metrics.get("minsk_qty", 0) or 0)
                if self.expose_legacy_availability
                else 0
            ),
            availability_status=availability_status,
            public_stock_state=(
                public_stock_state if self.expose_legacy_availability else None
            ),
            delivery_min_days=delivery_min_days,
            delivery_max_days=delivery_max_days,
        )


CANONICAL_PUBLIC_DISCLOSURE = PublicCatalogDisclosurePolicy(
    expose_legacy_availability=True,
    expose_source_provenance=True,
)
TENANT_NEUTRAL_PUBLIC_DISCLOSURE = PublicCatalogDisclosurePolicy(
    expose_legacy_availability=False,
    expose_source_provenance=False,
)


def resolve_public_stock_state(
    availability_status: str | None,
) -> tuple[str, int | None, int | None]:
    stock_state_map = {
        "in_stock_now": ("local_stock", 0, 0),
        "available_2_3_days": ("supplier_stock", 2, 3),
        "check_availability": ("available_to_order", None, None),
        "out_of_stock": ("out_of_stock", None, None),
    }
    return stock_state_map.get(
        availability_status,
        ("out_of_stock", None, None),
    )


__all__ = [
    "CANONICAL_PUBLIC_DISCLOSURE",
    "TENANT_NEUTRAL_PUBLIC_DISCLOSURE",
    "PublicCatalogDisclosurePolicy",
    "resolve_public_stock_state",
]
