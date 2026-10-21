"""Nominal cooling capacity; electrical input is never a capacity fallback."""

from __future__ import annotations

import math
from typing import Any

from services.spec_normalizer import clean_value


def nominal_cooling_capacity(specs: dict[str, Any] | None, *, fallback: Any = None) -> float | None:
    values = specs or {}
    raw = values.get("capacity_cooling_kw")
    if raw is not None and not isinstance(raw, bool):
        # Canonical numeric values are already kW. Do not reapply a donor's
        # watt-scale heuristic or turn non-finite exponent notation into 1.
        if isinstance(raw, str):
            try:
                raw = float(raw.strip().replace(",", "."))
            except ValueError:
                raw = clean_value("capacity_cooling_kw", raw, keep_units=False)
        try:
            capacity = float(raw)
        except (TypeError, ValueError, OverflowError):
            pass
        else:
            if math.isfinite(capacity) and capacity > 0:
                return capacity
    # A parser's explicit nominal metric supports sources without specs. It
    # must already distinguish capacity from consumption; see parser tests.
    if isinstance(fallback, bool):
        return None
    try:
        capacity = float(fallback)
    except (TypeError, ValueError, OverflowError):
        return None
    return capacity if math.isfinite(capacity) and capacity > 0 else None
