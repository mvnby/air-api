from __future__ import annotations

from dataclasses import dataclass


WAYBILL_DOCUMENT_TYPES = frozenset({"tn2", "ttn1"})


@dataclass(frozen=True, slots=True)
class TransportTerms:
    """Transport facts frozen into a native paper waybill draft."""

    car_model: str | None = None
    car_number: str | None = None
    driver_name: str | None = None
    carrier: str | None = None

