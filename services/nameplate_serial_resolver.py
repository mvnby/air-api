"""Deterministic, safety-first serial-number resolution for HVAC nameplates."""

from __future__ import annotations

import re
from typing import Any


SERIAL_LABEL_RE = re.compile(r"\b(?:SERIAL(?:\s*(?:NO|NUMBER|NUM))?|S\s*/?\s*N|CEREAL)\b", re.I)
BARCODE_LABEL_RE = re.compile(r"\b(?:BAR\s*CODE|BARCODE|ШТРИХ\s*-?\s*КОД)\b", re.I)
REJECT_CONTEXT_RE = re.compile(
    r"\b(?:MANUFACTURED|MANUFACTURE|MFG|DATE|VOLTAGE|CURRENT|POWER|CAPACITY|"
    r"REFRIGERANT|REFRI|CHARGE|PRESSURE|FREQUENCY|WEIGHT|MODEL|"
    r"ИЗГОТОВЛ|ДАТА|НАПРЯЖ|ТОК|МОЩНОСТ|ХЛАДАГЕНТ|ДАВЛЕН)\b",
    re.I,
)
UNIT_RE = re.compile(r"(?:\d)\s*(?:KG|КГ|W|KW|КВТ|V|В|A|А|HZ|ГЦ|MPA|KPA|PA|BTU|TONNES?)\b", re.I)
DATE_RE = re.compile(r"^(?:19|20)\d{2}[.\-/](?:0?[1-9]|1[0-2])(?:[.\-/](?:0?[1-9]|[12]\d|3[01]))?$")
TOKEN_RE = re.compile(r"\b[A-Z0-9][A-Z0-9._-]{4,}[A-Z0-9]\b", re.I)


def _identity(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _clean(value: Any) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "").upper()).strip(" .,:;")
    identity = _identity(text)
    if len(identity) < 5 or len(identity) > 64 or not re.search(r"\d", identity):
        return None
    return text


def _reject_reason(value: str, *, context: str = "") -> str | None:
    identity = _identity(value)
    combined = f"{context} {value}"
    if DATE_RE.fullmatch(value.replace(" ", "")):
        return "date"
    if UNIT_RE.search(combined):
        return "measurement"
    if REJECT_CONTEXT_RE.search(value):
        return "technical_label"
    if re.fullmatch(r"R\d{2,4}A?", identity):
        return "refrigerant"
    if context and REJECT_CONTEXT_RE.search(context) and not SERIAL_LABEL_RE.search(context):
        return "technical_context"
    if re.fullmatch(r"(?:19|20)\d{4,6}", identity):
        return "date_like"
    return None


def _brand_specific_bonus(candidate: str, brand: str | None, model: str | None) -> int:
    identity = _identity(candidate)
    looks_like_tcl = "TCL" in (brand or "").upper() or (model or "").upper().startswith("TAC-")
    if not looks_like_tcl:
        return -25 if re.fullmatch(r"MO\d+", identity) else 0
    score = 0
    if re.search(r"[A-Z]", identity) and re.search(r"\d", identity) and len(identity) >= 18:
        score += 95
    if re.fullmatch(r"MO\d+", identity):
        score -= 60
    if identity.isdigit() and len(identity) <= 12:
        score -= 35
    return score


def resolve_serial_number(
    raw: dict[str, Any],
    raw_text: str,
    *,
    equipment_model: str | None,
    brand: str | None,
) -> dict[str, Any]:
    """Return ranked candidates and whether a person must make the choice."""
    records: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, str]] = []
    model_identity = _identity(equipment_model or "")

    def add(value: Any, *, source: str, context: str = "", bonus: int = 0) -> None:
        cleaned = _clean(value)
        if not cleaned:
            return
        identity = _identity(cleaned)
        if identity == model_identity or (model_identity and identity in model_identity):
            return
        reason = _reject_reason(cleaned, context=context)
        if reason:
            if len(rejected) < 12:
                rejected.append({"value": cleaned, "reason": reason})
            return
        record = records.setdefault(
            identity,
            {"value": cleaned, "score": min(len(identity), 24), "sources": [], "evidence": []},
        )
        if source not in record["sources"]:
            record["sources"].append(source)
            record["score"] += bonus
        if context and context not in record["evidence"] and len(record["evidence"]) < 3:
            record["evidence"].append(context[:160])

    direct_keys = (
        "equipment_serial_number",
        "serial_number",
        "serial",
        "sn",
        "s_n",
        "barcode_text",
        "barcode_value",
        "barcode",
    )
    for key in direct_keys:
        value = raw.get(key)
        if value:
            add(
                value,
                source=f"field:{key}",
                bonus=55 if "serial" in key or key in {"sn", "s_n"} else 35,
            )
            for token in TOKEN_RE.findall(str(value)):
                add(token, source=f"field:{key}", bonus=55 if "serial" in key or key in {"sn", "s_n"} else 35)

    list_keys = (
        "serial_candidates",
        "serial_number_candidates",
        "serials",
        "barcode_values",
        "barcodes",
    )
    for key in list_keys:
        value = raw.get(key)
        values = value if isinstance(value, list) else list(value.values()) if isinstance(value, dict) else [value]
        for item in values:
            add(item, source=f"field:{key}", bonus=25)
            for token in TOKEN_RE.findall(str(item or "")):
                add(token, source=f"field:{key}", bonus=25)

    lines = [re.sub(r"\s+", " ", line).strip() for line in str(raw_text or "").splitlines()]
    for index, line in enumerate(lines):
        serial_label = bool(SERIAL_LABEL_RE.search(line))
        barcode_label = bool(BARCODE_LABEL_RE.search(line))
        for distance in range(0, 3 if serial_label or barcode_label else 1):
            if index + distance >= len(lines):
                break
            candidate_line = lines[index + distance]
            context = " | ".join(lines[index : min(len(lines), index + distance + 1)])
            for token in TOKEN_RE.findall(candidate_line):
                bonus = 0
                source = "ocr"
                if serial_label:
                    bonus = 85 - distance * 22
                    source = "serial_label"
                elif barcode_label:
                    bonus = 55 - distance * 15
                    source = "barcode_label"
                add(token, source=source, context=context, bonus=bonus)

    for record in records.values():
        identity = _identity(record["value"])
        if identity.isdigit() and 11 <= len(identity) <= 14:
            record["score"] += 38
            record["sources"].append("numeric_barcode_shape")
        if re.search(r"[A-Z]", identity) and re.search(r"\d", identity):
            record["score"] += 18
        record["score"] += _brand_specific_bonus(record["value"], brand, equipment_model)

    ranked = sorted(records.values(), key=lambda item: (-int(item["score"]), str(item["value"])))[:8]
    if not ranked:
        return {"candidates": [], "details": [], "selected": None, "selection_required": False, "rejected": rejected}

    top = ranked[0]
    runner_up_score = int(ranked[1]["score"]) if len(ranked) > 1 else -999
    has_strong_evidence = bool(
        {"serial_label", "barcode_label", "numeric_barcode_shape"}.intersection(top["sources"])
        or any(str(source).startswith("field:serial") or source in {"field:sn", "field:s_n"} for source in top["sources"])
    )
    selection_required = not (has_strong_evidence and int(top["score"]) - runner_up_score >= 18)
    selected = str(top["value"])
    return {
        "candidates": [str(item["value"]) for item in ranked],
        "details": ranked,
        "selected": selected,
        "selection_required": selection_required,
        "selection": {
            "source": "auto",
            "value": selected,
            "evidence": list(top["sources"]),
            "score": int(top["score"]),
        },
        "rejected": rejected,
    }
