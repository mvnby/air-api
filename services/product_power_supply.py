"""Conservative client text from stated electrical specifications only."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from services.spec_normalizer import normalize_specs
from services.spec_registry import REGISTRY_KEY_MAP

_VOLTAGE = re.compile(r"(?<![\d.,])([1-6]\d{2})(?:\s*-\s*([1-6]\d{2}))?(?![\d.,])")
_UNKNOWN = re.compile(
    r"\?|не\s*(?:извест|указ|определ|подтвержд)|уточн|предполож|возмож|по запросу|unknown|\bn/?a\b",
    re.I,
)


@dataclass(frozen=True)
class _Supply:
    text: str
    lower: int
    upper: int
    phase: str | None
    uncertain: bool = False
    conflicting_aliases: bool = False

    @property
    def display(self) -> str:
        return self.text + (" (требует уточнения)" if self.uncertain else "")


def _supply(value: Any) -> _Supply | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    raw = re.sub(r"\s+", " ", str(value)).strip()
    raw = re.sub(r"[–—]", "-", raw)
    raw = re.sub(r"(?<=\d)\s*[~～]\s*(?=\d)", "-", raw)
    if _UNKNOWN.search(raw):
        return None
    matches = list(_VOLTAGE.finditer(raw))
    if not matches:
        return None
    # Values containing block names carry their own scope. Keep that wording.
    phase = None
    if re.search(r"внутр|наруж|внешн", raw, re.I):
        text = _VOLTAGE.sub(lambda m: m.group(0) + ("" if re.match(r"\s*[вv]", raw[m.end():], re.I) else " В"), raw)
    else:
        voltages = [m.group(1) + (f"-{m.group(2)}" if m.group(2) else "") for m in matches]
        text = "/".join(dict.fromkeys(voltages)) + " В"
        phase = re.search(r"(?<!\d)([13])\s*(?:ф|ph|n?\s*[~∼])", raw, re.I)
        if not phase:
            # Source tables use either Ф/В/Гц or В/Гц/Ф.
            phase = re.search(r"^\s*([13])\s*/", raw) or re.search(r"/\s*([13])\s*$", raw)
        if phase:
            text += f", {phase.group(1)} ф."
        if re.search(r"нейтрал|[13]\s*n\s*[~∼]", raw, re.I):
            text += ", нейтраль"
    bounds = [int(n) for match in matches for n in match.groups() if n]
    scoped = bool(re.search(r"внутр|наруж|внешн", raw, re.I))
    return _Supply(text, min(bounds), max(bounds), phase.group(1) if phase else None,
        uncertain=len(matches) > 1 and not scoped)


def _overlaps(first: _Supply, second: _Supply) -> bool:
    return (not first.uncertain and not second.uncertain
            and first.lower <= second.upper and second.lower <= first.upper
            and not (first.phase and second.phase and first.phase != second.phase))


def _field_supply(specs: dict, key: str) -> _Supply | None:
    # Normalize the keys through the registry, but inspect every source value:
    # normalize_specs alone would silently pick one conflicting alias.
    values = [_supply(value) for name, value in specs.items()
        if REGISTRY_KEY_MAP.get(name, name) == key]
    known = list({value.text: value for value in values if value}.values())
    if not known:
        return None
    if any(not _overlaps(first, second) for first in known for second in known if first is not second):
        return _Supply(" / ".join(value.text for value in known),
            min(value.lower for value in known), max(value.upper for value in known), None, True, True)
    return next((value for value in known if value.phase), known[0])


def _resolve_block_aggregate(value: _Supply | None, blocks: list[tuple[str, _Supply]]) -> _Supply | None:
    """Suppress a redundant summary only when both explicit blocks prove it."""
    if not value or len(blocks) != 2 or any(block.uncertain for _, block in blocks):
        return value
    ranges = [(int(m.group(1)), int(m.group(2) or m.group(1))) for m in _VOLTAGE.finditer(value.text)]
    if len(ranges) < 2:
        return value
    resolved = False
    if not value.conflicting_aliases:
        if re.search(r"внутр|наруж|внешн", value.text, re.I):
            segments = value.text.split(";")
            matched = set()
            for segment in segments:
                label, separator, parameters = segment.partition(":")
                role = "внутреннего блока" if re.search(r"внутр", label, re.I) else (
                    "наружного блока" if re.search(r"наруж|внешн", label, re.I) else None
                )
                stated = _supply(parameters) if separator else None
                block = dict(blocks).get(role)
                if (stated and block and not stated.uncertain and _overlaps(stated, block)
                        and (stated.lower, stated.upper) == (block.lower, block.upper)
                        and (not stated.phase or stated.phase == block.phase)
                        and ("нейтраль" not in stated.text or "нейтраль" in block.text)):
                    matched.add(role)
            resolved = len(segments) == len(matched) == 2
        else:
            resolved = not value.phase and set(ranges) == {(block.lower, block.upper) for _, block in blocks}
    return None if resolved else replace(value, uncertain=True)


def build_product_power_supply_description(specs: Any, product_kind: str | None = None) -> str:
    """Keep block scope and conflicting source values visible; infer no wiring."""
    raw = specs if isinstance(specs, dict) else {}
    normalized = normalize_specs(raw)
    general = _field_supply(raw, "power_supply")
    voltage = _field_supply(raw, "power_supply_voltage")
    blocks = [(label, supply) for label, key in (
        ("внутреннего блока", "power_supply_indoor"),
        ("наружного блока", "power_supply_outdoor"),
    ) if (supply := _field_supply(raw, key))]
    general = _resolve_block_aggregate(general, blocks)
    voltage = _resolve_block_aggregate(voltage, blocks)
    parts = [f"параметры питания {label}: {supply.display}" for label, supply in blocks]
    if general and voltage and not _overlaps(general, voltage):
        parts.append(f"питание по общим данным: {general.text} / {voltage.text} (требует уточнения)")
    else:
        common = general or voltage
        covered = common and any(
            _overlaps(common, supply)
            and (not common.phase or common.phase == supply.phase)
            and ("нейтраль" not in common.text or "нейтраль" in supply.text)
            and supply.lower <= common.lower <= common.upper <= supply.upper
            for _, supply in blocks
        )
        if common and not covered:
            label = "питание по общим данным" if blocks else "питание"
            suffix = " (требует уточнения)" if blocks and not any(
                _overlaps(common, supply) for _, supply in blocks
            ) else ""
            parts.append(f"{label}: {common.display}{suffix if not common.uncertain else ''}")
    if parts:
        location = str(normalized.get("power_supply_location") or "").lower()
        indoor = bool(re.search(r"внутр", location))
        outdoor = bool(re.search(r"наруж|внешн|нруж", location))
        if indoor or outdoor:
            target = "к внутреннему и наружному блокам" if indoor and outdoor else (
                "к внутреннему блоку" if indoor else "к наружному блоку"
            )
            parts.append(f"подключение питания: {target}")
    if not parts:
        kind = product_kind or normalized.get("product_kind") or "unknown"
        air_conditioner = kind in {"complete_split_system", "indoor_unit", "outdoor_unit"}
        if kind not in {"accessory", "consumable", "panel"} and not air_conditioner:
            air_conditioner = normalized.get("type") in {
                "сплит-система", "мульти-сплит-система", "полупромышленный кондиционер",
                "внутренний блок", "наружный блок",
            } or normalized.get("indoor_type_kind") in {
                "wall", "cassette", "duct", "floor_ceiling", "column", "console",
            }
        if air_conditioner:
            return "питание: уточняется"
    return "; ".join(parts)
