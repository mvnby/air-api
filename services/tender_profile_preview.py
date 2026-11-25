"""Preview a draft filter using the company's existing tender records."""

import re

from schemas_tender_search import (
    TenderLotSignals, TenderPlace, TenderProfilePreview, TenderProfilePreviewItem, TenderSearchProfile, normalized_place,
)
from services.tender_qualification import _INSTALL_INCLUDED, _NO_WORKS, _NON_OBLIGATION, _SCOPE_NEGATION, _scope_patterns
from services.tender_search_matcher import match_tender_lot

_DIRECTIONS = {
    "air_conditioning": r"(?:кондиционер\w*|кондиционировани\w*|сплит[\s-]*систем\w*)",
    "ventilation": r"(?:вентиляц\w*|вентиляционн\w+\s+(?:оборудовани\w*|систем\w*))",
    "refrigeration": r"(?:холодильник\w*|холодильн\w+\s+(?:оборудовани\w*|камер\w*|шкаф\w*|агрегат\w*|установк\w*))",
}
_DIRECTION_PATTERNS = {key: re.compile(rf"\b{value}\b", re.I) for key, value in _DIRECTIONS.items()}
_WORK_PATTERNS = {key: _scope_patterns(value) for key, value in _DIRECTIONS.items()}
_REGION_PATTERNS = {
    "1": r"\bбрестск\w+ област\w*\b|\b(?:г )?брест\b",
    "2": r"\bвитебск\w+ област\w*\b|\b(?:г )?витебск\b",
    "3": r"\bгомельск\w+ област\w*\b|\b(?:г )?гомель\b",
    "4": r"\bгродненск\w+ област\w*\b|\b(?:г )?гродно\b",
    "5": r"\b(?:г )?минск\b",
    "6": r"\bминск\w+ област\w*\b",
    "7": r"\bмогилевск\w+ област\w*\b|\b(?:г )?могилев\b",
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
        result = match_tender_lot(profile, _classify(title, enrichment if isinstance(enrichment, dict) else {}))
        items.append(TenderProfilePreviewItem(order_id=order_id, title=title, result=result))
    return TenderProfilePreview(items=items)
