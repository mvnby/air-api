"""Bounded native lot fields transported by the collector feed."""

import re

_LIMITS = {
    "number": 60, "name": 1000, "quantity": 100, "estimated_value": 100,
    "status": 80, "okrb": 40, "delivery_place": 700, "delivery_period": 100,
}
_LOT_LIMIT = 20


def native_lot_snapshot(tender: dict) -> dict:
    value = tender.get("lots")
    if tender.get("source") != "goszakupki_by" or not isinstance(value, list) or not value:
        return {}
    lots = []
    numbers = set()
    complete = tender.get("lot_inventory_complete") is True and len(value) <= _LOT_LIMIT
    for row in value[:_LOT_LIMIT]:
        if not isinstance(row, dict):
            complete = False
            continue
        clean = {}
        for key, limit in _LIMITS.items():
            item = row.get(key)
            if isinstance(item, str) and item.strip():
                item = " ".join(item.split())
                if len(item) > limit:
                    complete = False
                clean[key] = item[:limit]
        number = clean.get("number", "")
        if not re.fullmatch(r"[1-9][0-9]*", number) or not clean.get("name") or number in numbers:
            complete = False
            continue
        numbers.add(number)
        lots.append(clean)
    return {"lots": lots, "lot_inventory_complete": complete} if lots else {}
