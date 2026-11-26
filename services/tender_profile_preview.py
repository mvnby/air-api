"""Preview a draft filter using the company's existing tender records."""

import re

from schemas_tender_search import (
    TenderLotSignals, TenderPlace, TenderProfilePreview, TenderProfilePreviewItem, TenderSearchProfile, normalized_place,
)
from services.tender_lot_snapshot import native_lot_snapshot
from services.tender_qualification import (
    _INSTALL_INCLUDED, _NO_WORKS, _NON_OBLIGATION, _OBJECT_MODIFIERS, _SCOPE_NEGATION, _scope_patterns,
)
from services.tender_search_matcher import match_tender_lot

_DIRECTIONS = {
    "air_conditioning": r"(?:кондиционер\w*|кондиционировани\w*|сплит[\s-]*систем\w*)",
    "ventilation": r"(?:вентиляц\w*|вентиляционн\w+\s+(?:оборудовани\w*|систем\w*))",
    "refrigeration": r"(?:холодильник\w*|холодильн\w+\s+(?:оборудовани\w*|камер\w*|шкаф\w*|агрегат\w*|установк\w*)|оборудовани\w*\s+холодильн\w*)",
}
_DIRECTION_PATTERNS = {key: re.compile(rf"\b{value}\b", re.I) for key, value in _DIRECTIONS.items()}
_EQUIPMENT = "(?:" + "|".join(_DIRECTIONS.values()) + ")"
_EQUIPMENT_OBJECT = rf"{_EQUIPMENT}\b(?:\s+воздуха\b)?"
_EQUIPMENT_JOIN = r"(?:\s*,\s*(?:и\s+)?|\s+и\s+)"
_RELATED_EQUIPMENT = rf"(?:{_EQUIPMENT_OBJECT}{_EQUIPMENT_JOIN}{_OBJECT_MODIFIERS}{{0,5}}){{0,2}}"
_WORK_PATTERNS = {key: _scope_patterns(_RELATED_EQUIPMENT + value) for key, value in _DIRECTIONS.items()}
_ALTERNATIVE_SCOPE = re.compile(
    rf"\b{_EQUIPMENT_OBJECT}(?:\s+(?:или|либо)\s+|\s+и\s*\(\s*или\s*\)\s*|\s*/\s*)"
    rf"{_OBJECT_MODIFIERS}{{0,5}}{_EQUIPMENT}\b|\b(?:при\s+необходимости|опциональн\w*)\b", re.I,
)
_INSTALL_AFTER_SUPPLY = re.compile(
    rf"(?:\s+воздуха\b)?(?:{_EQUIPMENT_JOIN}{_OBJECT_MODIFIERS}{{0,5}}{_EQUIPMENT_OBJECT}){{0,2}}"
    rf"\s*(?:,\s*)?{_INSTALL_INCLUDED.pattern}", re.I,
)
_VENTILATION_INSTALLATION = re.compile(
    r"\bработ\w*\s+по\s+устройств\w*\s+(?:систем\w*\s+)?вентиляц\w*\b", re.I,
)
_OBLAST = r"обл(?:аст\w*)?\b"
_REGION_PATTERNS = {
    "1": rf"\bбрестск\w+ {_OBLAST}|\b(?:г )?брест\b",
    "2": rf"\bвитебск\w+ {_OBLAST}|\b(?:г )?витебск\b",
    "3": rf"\bгомельск\w+ {_OBLAST}|\b(?:г )?гомель\b",
    "4": rf"\bгродненск\w+ {_OBLAST}|\b(?:г )?гродно\b",
    "5": r"\b(?:г )?минск\b",
    "6": rf"\bминск\w+ (?:{_OBLAST}|район\w*\b|р н\b)",
    "7": rf"\bмогилевск\w+ {_OBLAST}|\b(?:г )?могилев\b",
}


def _places(objects) -> tuple[list[TenderPlace], bool]:
    if not isinstance(objects, list):
        return [], False
    places = []
    for site in objects[:30]:
        if not isinstance(site, dict) or not isinstance(site.get("address"), str):
            continue
        address = normalized_place(site["address"])
        found = [code for code, cue in _REGION_PATTERNS.items() if re.search(cue, address)]
        if len(found) == 1 and len(address) >= 2:
            places.append(TenderPlace(region=found[0], locality=address[:150]))
    return places, bool(places) and len(places) == len(objects)


def _installation_for_direction(clause: str, direction: str) -> bool:
    for supply in _WORK_PATTERNS[direction]["supply_only"].finditer(clause):
        installation = _INSTALL_AFTER_SUPPLY.match(clause, supply.end())
        if installation and not any(
            other != direction and pattern.search(clause, installation.end())
            for other, pattern in _DIRECTION_PATTERNS.items()
        ):
            return True
    return False


def _classify(title: str, enrichment: dict, *, verified_lot: bool = False, headline: str = "") -> TenderLotSignals:
    summary = enrichment.get("work_summary")
    reviewed = summary if isinstance(summary, str) else ""
    subject = f"{title}\n{reviewed}"
    directions = {key for key, pattern in _DIRECTION_PATTERNS.items() if pattern.search(subject) or pattern.search(headline)}
    activities_by_direction = {}
    for clause in re.split(r"[;\n]", subject):
        if _NON_OBLIGATION.search(clause) or _ALTERNATIVE_SCOPE.search(clause):
            continue
        negation = _SCOPE_NEGATION.search(clause)
        no_works = _NO_WORKS.search(clause)
        if negation:
            if not no_works or not no_works.start() <= negation.start() < no_works.end():
                continue
            clause = clause[:no_works.start()]
        for direction in directions:
            found = {kind for kind, pattern in _WORK_PATTERNS[direction].items() if pattern.search(clause)}
            if direction == "ventilation" and _VENTILATION_INSTALLATION.search(clause):
                found.add("installation")
            if "supply_only" in found:
                found.remove("supply_only")
                found.add("supply")
                if not no_works and _installation_for_direction(clause, direction):
                    found.add("installation")
            if no_works:
                found.discard("installation")
            if found:
                activities_by_direction.setdefault(direction, []).append(found)
    places, places_complete = _places(enrichment.get("objects"))
    confirmed_directions = set(activities_by_direction)
    # A mixed procedure heading cannot establish which obligations share a lot.
    mixed_scope = not verified_lot and (
        len(confirmed_directions) > 1 or re.search(r"\bлот\s*(?:№\s*)?\d+", subject, re.I) is not None
    )
    activity_groups = [group for groups in activities_by_direction.values() for group in groups]
    distinct_activity_groups = {frozenset(group) for group in activity_groups}
    return TenderLotSignals(
        lot_key="procedure",
        confirmed_directions=set() if mixed_scope else confirmed_directions,
        possible_directions=directions if mixed_scope else directions - confirmed_directions,
        required_activities=set() if mixed_scope else set().union(*activity_groups),
        activity_evidence_by_direction={} if mixed_scope else activities_by_direction,
        execution_places=[] if mixed_scope else places,
        places_complete=places_complete and not mixed_scope,
        directions_complete=bool(reviewed and confirmed_directions) and not mixed_scope,
        activities_complete=bool(reviewed and len(distinct_activity_groups) == 1) and not mixed_scope,
        verified_native_lot=verified_lot,
    )


def publication_signals(
    title: str, tender: dict, *, reviewed: dict | None = None, active_lots_only: bool = False,
) -> tuple[list[TenderLotSignals], bool]:
    context = reviewed or {}
    snapshot = native_lot_snapshot(tender)
    lots = snapshot.get("lots", [])
    if not lots:
        return [_classify(title, context)], False
    verified_lots = snapshot["lot_inventory_complete"]
    one_lot = verified_lots and len(lots) == 1
    signals = []
    for lot in lots:
        if active_lots_only and lot.get("status", "").casefold() in {"отменен", "отменён", "отменена", "завершен", "завершён", "завершена"}:
            continue
        lot_context = dict(context) if one_lot else {}
        if lot.get("delivery_place"):
            objects = lot_context.get("objects")
            known = objects if isinstance(objects, list) else []
            lot_context["objects"] = [*known, {"address": lot["delivery_place"]}]
        lot_signals = _classify(lot["name"], lot_context, verified_lot=verified_lots, headline=title if one_lot else "")
        lot_signals.lot_key = lot["number"]
        signals.append(lot_signals)
    if not signals:
        return [TenderLotSignals(
            lot_key="procedure", directions_complete=snapshot["lot_inventory_complete"],
        )], False
    return signals, True


def match_publication_signals(classified: tuple[list[TenderLotSignals], bool], profile: TenderSearchProfile):
    signals, per_lot = classified
    matches = [match_tender_lot(profile, lot) for lot in signals]
    priority = {"match": 0, "review": 1, "excluded": 2}
    return min(matches, key=lambda match: priority[match.state]), matches if per_lot else []


def match_publication(title: str, tender: dict, profile: TenderSearchProfile, *, reviewed: dict | None = None):
    return match_publication_signals(publication_signals(title, tender, reviewed=reviewed), profile)


def preview_tender_profile(rows, profile: TenderSearchProfile) -> TenderProfilePreview:
    items = []
    for order_id, meta in rows:
        binding = meta.get("belzakupki") if isinstance(meta, dict) else None
        tender = binding.get("tender") if isinstance(binding, dict) else None
        if not isinstance(tender, dict):
            continue
        title = tender.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        enrichment = binding.get("enrichment")
        result, matches = match_publication(title, tender, profile,
                                            reviewed=enrichment if isinstance(enrichment, dict) else None)
        items.append(TenderProfilePreviewItem(order_id=order_id, title=title, result=result, lots=matches))
    return TenderProfilePreview(items=items)
