"""Preview a draft filter using the company's existing tender records."""

import re

from schemas_tender_search import (
    TenderLotSignals, TenderPlace, TenderProfilePreview, TenderProfilePreviewItem, TenderSearchProfile, normalized_place,
)
from services.tender_lot_snapshot import native_lot_snapshot
from services.tender_qualification import _INSTALL_INCLUDED, _NO_WORKS, _NON_OBLIGATION, _SCOPE_NEGATION, _scope_patterns
from services.tender_search_matcher import match_tender_lot

_DIRECTIONS = {
    "air_conditioning": r"(?:кондиционер\w*|кондиционировани\w*|сплит[\s-]*систем\w*)",
    "ventilation": r"(?:вентиляц\w*|вентиляционн\w+\s+(?:оборудовани\w*|систем\w*))",
    "refrigeration": r"(?:холодильник\w*|холодильн\w+\s+(?:оборудовани\w*|камер\w*|шкаф\w*|агрегат\w*|установк\w*)|оборудовани\w*\s+холодильн\w*)",
}
_DIRECTION_PATTERNS = {key: re.compile(rf"\b{value}\b", re.I) for key, value in _DIRECTIONS.items()}
_WORK_PATTERNS = {key: _scope_patterns(value) for key, value in _DIRECTIONS.items()}
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


def _classify(title: str, enrichment: dict) -> TenderLotSignals:
    summary = enrichment.get("work_summary")
    reviewed = summary if isinstance(summary, str) else ""
    subject = f"{title}\n{reviewed}"
    directions = {key for key, pattern in _DIRECTION_PATTERNS.items() if pattern.search(subject)}
    confirmed_directions = set()
    activity_groups = []
    for clause in re.split(r"[;\n]", subject):
        if (_SCOPE_NEGATION.search(clause) and not _NO_WORKS.search(clause)) or _NON_OBLIGATION.search(clause):
            continue
        for direction in directions:
            found = {kind for kind, pattern in _WORK_PATTERNS[direction].items() if pattern.search(clause)}
            if direction == "ventilation" and _VENTILATION_INSTALLATION.search(clause):
                found.add("installation")
            if not found:
                continue
            confirmed_directions.add(direction)
            if "supply_only" in found:
                found.remove("supply_only")
                found.add("supply")
                if _INSTALL_INCLUDED.search(clause) and not _NO_WORKS.search(clause):
                    found.add("installation")
                elif _NO_WORKS.search(clause):
                    found.discard("installation")
            activity_groups.append(found)
    places, places_complete = _places(enrichment.get("objects"))
    # Order snapshots lack per-lot conditions. Keep separately worded actions
    # separate and route mixed directions to review until lots can be checked.
    mixed_scope = len(confirmed_directions) > 1 or re.search(r"\bлот\s*(?:№\s*)?\d+", subject, re.I) is not None
    distinct_activity_groups = {frozenset(group) for group in activity_groups}
    return TenderLotSignals(
        lot_key="procedure",
        confirmed_directions=set() if mixed_scope else confirmed_directions,
        possible_directions=directions if mixed_scope else directions - confirmed_directions,
        required_activities=set() if mixed_scope else set().union(*activity_groups),
        activity_evidence_groups=[] if mixed_scope else activity_groups,
        execution_places=[] if mixed_scope else places,
        places_complete=places_complete and not mixed_scope,
        directions_complete=bool(reviewed and confirmed_directions) and not mixed_scope,
        activities_complete=bool(reviewed and len(distinct_activity_groups) == 1) and not mixed_scope,
    )


def publication_signals(
    title: str, tender: dict, *, reviewed: dict | None = None, active_lots_only: bool = False,
) -> tuple[list[TenderLotSignals], bool]:
    context = reviewed or {}
    snapshot = native_lot_snapshot(tender)
    lots = snapshot.get("lots", [])
    if not lots:
        return [_classify(title, context)], False
    one_lot = snapshot["lot_inventory_complete"] and len(lots) == 1
    signals = []
    for lot in lots:
        if active_lots_only and lot.get("status", "").casefold() in {"отменен", "отменён", "отменена", "завершен", "завершён", "завершена"}:
            continue
        lot_context = dict(context) if one_lot else {}
        if lot.get("delivery_place"):
            objects = lot_context.get("objects")
            known = objects if isinstance(objects, list) else []
            lot_context["objects"] = [*known, {"address": lot["delivery_place"]}]
        subject = f"{title}\n{lot['name']}" if one_lot else lot["name"]
        lot_signals = _classify(subject, lot_context)
        lot_signals.lot_key = lot["number"]
        lot_signals.verified_native_lot = snapshot["lot_inventory_complete"]
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
