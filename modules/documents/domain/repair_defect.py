"""Client-facing conclusion for one identified unit or paired equipment system."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator
from pydantic.dataclasses import dataclass


RepairVerdict = Literal["repairable", "not_repairable", "uneconomical", "needs_diagnostics", "operational"]
VERDICT_LABELS = {
    "repairable": "Оборудование подлежит ремонту",
    "not_repairable": "Оборудование не подлежит ремонту",
    "uneconomical": "Ремонт экономически нецелесообразен",
    "needs_diagnostics": "Для решения о ремонте нужна дополнительная диагностика",
    "operational": "Оборудование исправно",
}


@dataclass(frozen=True, config=ConfigDict(extra="forbid", str_strip_whitespace=True))
class RepairDefect:
    equipment: Annotated[str, Field(min_length=1, max_length=250)]
    verdict: RepairVerdict
    finding: Annotated[str, Field(min_length=1, max_length=320)]
    recommendation: Annotated[str, Field(min_length=1, max_length=320)]
    restriction: Annotated[str, Field(max_length=180)] | None = None
    cost: Annotated[str, Field(max_length=120)] | None = None
    term: Annotated[str, Field(max_length=120)] | None = None

    @field_validator("equipment", "finding", "recommendation", "restriction", "cost", "term", mode="before")
    @classmethod
    def compact_text(cls, value):
        # Each input is a short statement. Pasted line breaks must not stretch a one-page act.
        return " ".join(value.split()) if isinstance(value, str) else value

    def values(self) -> dict[str, str]:
        quote_expected = self.verdict in {"repairable", "needs_diagnostics"}
        estimate_note = ""
        if quote_expected and not self.cost and not self.term:
            estimate_note = (
                "Стоимость и срок ремонта уточняются после диагностики."
                if self.verdict == "needs_diagnostics"
                else "Стоимость и срок ремонта пока не определены."
            )
        return {
            "repair.estimate_note": estimate_note,
            "repair.equipment": self.equipment,
            "repair.verdict": VERDICT_LABELS[self.verdict],
            "repair.finding": self.finding,
            "repair.recommendation": self.recommendation,
            "repair.restriction": self.restriction or "",
            "repair.cost": self.cost or ("Подлежит уточнению" if quote_expected else ""),
            "repair.term": self.term or ("Подлежит уточнению" if quote_expected else ""),
        }

    def update_snapshot(self, snapshot: dict) -> None:
        values = self.values()
        snapshot["values"].update(values)
        conditions = snapshot["conditions"]
        grouped = bool(values["repair.estimate_note"])
        conditions["repair.has_estimate_note"] = grouped
        conditions["repair.has_restriction"] = bool(self.restriction)
        for name in ("cost", "term"):
            conditions[f"repair.has_{name}"] = bool(values[f"repair.{name}"]) and not grouped
