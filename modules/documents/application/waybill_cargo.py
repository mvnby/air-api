"""Measured shipment facts belong to the printed rows of one frozen TTN draft."""

from copy import deepcopy
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from .value_formatters import number_in_words, quantity


class WaybillCargoMeasure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_number: int = Field(strict=True, gt=0)
    seats: int | None = Field(default=None, strict=True, gt=0, le=999_999_999)
    mass_kg: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)


class WaybillCargoLine(WaybillCargoMeasure):
    title: str
    quantity: str
    unit: str


def draft_snapshot_copy(snapshot: dict) -> dict:
    """Use a working copy for preview, external editing and first issuance."""
    result = deepcopy(snapshot)
    if result.get("meta", {}).get("document_type") not in {"ttn1", "tn2"}:
        return result
    values = result.get("values", {})
    rows = result.get("table_rows", {}).get("lines", [])
    if "totals.seats" in values or not all(
        row.get("line.mass") == "0.00" and row.get("line.seats") == row.get("line.quantity")
        for row in rows
    ):
        return result
    # The legacy native builder always assigned goods quantity as places and zero as weight.
    for row in rows:
        row["line.seats"] = row["line.mass"] = ""
    for name in ("totals.seats", "totals.seats_in_words", "totals.weight", "totals.weight_in_words"):
        values[name] = ""
    return result


def cargo_lines(snapshot: dict) -> list[dict]:
    confirmed = snapshot.get("meta", {}).get("waybill_cargo_entered") is True
    # Older drafts contain assumed seats and a zero mass. Only reuse measurements
    # explicitly saved for this document.
    return [
        {
            "line_number": int(row["line.number"]),
            "title": row["line.title"],
            "quantity": row["line.quantity"],
            "unit": row.get("line.unit", ""),
            "seats": int(row["line.seats"]) if confirmed and row.get("line.seats") else None,
            "mass_kg": (row.get("line.mass") or None) if confirmed else None,
        }
        for row in snapshot.get("table_rows", {}).get("lines", [])
    ]


def apply_cargo_measures(snapshot: dict, measures: list[dict]) -> None:
    rows = snapshot["table_rows"]["lines"]
    by_number = {int(row["line.number"]): row for row in rows}
    parsed = [WaybillCargoMeasure.model_validate(item) for item in measures]
    if len(parsed) != len(rows) or {m.line_number for m in parsed} != set(by_number):
        raise ValueError("Состав груза изменился. Откройте параметры черновика заново")
    for measure in parsed:
        row = by_number[measure.line_number]
        row["line.seats"] = str(measure.seats) if measure.seats is not None else ""
        row["line.mass"] = quantity(measure.mass_kg) if measure.mass_kg is not None else ""
    values = snapshot["values"]
    for field, total in (("line.seats", "totals.seats"), ("line.mass", "totals.weight")):
        complete = bool(rows) and all(row[field] for row in rows)
        if complete:
            amount = sum(Decimal(row[field]) for row in rows)
            values[total], values[total + "_in_words"] = quantity(amount), number_in_words(amount.normalize())
        else:
            values[total], values[total + "_in_words"] = "", ""
    snapshot["meta"]["waybill_cargo_entered"] = True
