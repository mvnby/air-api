"""Validation helpers for the reviewed catalog area backfill plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}


class CatalogAreaPlanError(ValueError):
    """Raised when a reviewed area plan is malformed or unsafe to apply."""


@dataclass(frozen=True)
class CatalogAreaPlanEntry:
    product_id: int
    model: str
    proposed_area_m2: int | None
    source: str
    confidence: str
    explanation: str
    status: str

    @property
    def is_candidate(self) -> bool:
        return self.status == "candidate"


def load_plan_entries(payload: dict[str, Any]) -> list[CatalogAreaPlanEntry]:
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raise CatalogAreaPlanError("plan must contain an entries list")

    seen_ids: set[int] = set()
    entries: list[CatalogAreaPlanEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise CatalogAreaPlanError("each plan entry must be an object")
        product_id = raw_entry.get("product_id")
        model = raw_entry.get("model")
        confidence = raw_entry.get("confidence")
        status = raw_entry.get("status")
        proposed_area_m2 = raw_entry.get("proposed_area_m2")
        if not isinstance(product_id, int) or product_id <= 0 or product_id in seen_ids:
            raise CatalogAreaPlanError("product_id values must be unique positive integers")
        if not isinstance(model, str) or not model.strip():
            raise CatalogAreaPlanError(f"entry {product_id} must define a model")
        if confidence not in CONFIDENCE_RANK:
            raise CatalogAreaPlanError(f"entry {product_id} has unknown confidence")
        if status not in {"candidate", "not_applicable", "insufficient_data"}:
            raise CatalogAreaPlanError(f"entry {product_id} has unknown status")
        if status == "candidate" and (
            not isinstance(proposed_area_m2, int) or proposed_area_m2 <= 0
        ):
            raise CatalogAreaPlanError(f"candidate {product_id} must have a positive integer area")
        if status != "candidate" and proposed_area_m2 is not None:
            raise CatalogAreaPlanError(f"non-candidate {product_id} must not have an area")

        seen_ids.add(product_id)
        entries.append(
            CatalogAreaPlanEntry(
                product_id=product_id,
                model=model.strip(),
                proposed_area_m2=proposed_area_m2,
                source=str(raw_entry.get("source") or "").strip(),
                confidence=confidence,
                explanation=str(raw_entry.get("explanation") or "").strip(),
                status=status,
            )
        )
    return entries


def should_apply(entry: CatalogAreaPlanEntry, minimum_confidence: str) -> bool:
    return entry.is_candidate and CONFIDENCE_RANK[entry.confidence] >= CONFIDENCE_RANK[minimum_confidence]


def build_specs_update(specs: dict[str, Any] | None, entry: CatalogAreaPlanEntry) -> dict[str, Any] | None:
    """Return an update only for a missing canonical area; never overwrite data."""
    current_specs = dict(specs or {})
    existing_area = str(current_specs.get("area_m2") or "").strip()
    if existing_area or not entry.is_candidate or entry.proposed_area_m2 is None:
        return None

    current_specs["area_m2"] = str(entry.proposed_area_m2)
    return current_specs
