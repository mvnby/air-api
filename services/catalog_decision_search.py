"""Interpret explicitly labelled cooling capacity in catalog search text."""

from __future__ import annotations

import re

_COOLING_KW = re.compile(r"(?<![\w.,+\-])(\d+(?:[.,]\d+)?)\s*(?:квт|kw)(?![\w-])", re.IGNORECASE)


def split_catalog_decision_search(search: str) -> tuple[list[str], tuple[float, ...]]:
    """Keep text tokens separate from exact, explicitly labelled kW values.

    A bare ``7`` retains the existing BTU smart-search meaning; ``7 кВт``
    identifies nominal cooling capacity and must never search the unit in titles.
    Explicit kW units fix the scale; donor watt heuristics do not apply.
    """
    capacities = tuple(
        float(match.group(1).replace(",", "."))
        for match in _COOLING_KW.finditer(search)
    )
    return _COOLING_KW.sub(" ", search).split(), capacities
