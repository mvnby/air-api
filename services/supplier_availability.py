from __future__ import annotations

import re


IN_STOCK_PATTERNS = (
    "в наличии",
    "наличии",
    "есть",
    "available",
    "in stock",
)
INCOMING_PATTERNS = (
    "ожида",
    "приход",
    "поставка",
    "под заказ",
    "incoming",
)
OUT_PATTERNS = (
    "нет в наличии",
    "нет налич",
    "out of stock",
    "отсутств",
)


def classify_availability(raw: str | None) -> str:
    text = (raw or "").strip().lower()
    if not text:
        return "unknown"

    if any(p in text for p in OUT_PATTERNS):
        return "out_of_stock"
    if any(p in text for p in INCOMING_PATTERNS):
        return "incoming"
    if any(p in text for p in IN_STOCK_PATTERNS):
        return "in_stock"
    return "unknown"


def parse_qty_with_text_fallback(raw: str | None) -> int:
    text = (raw or "").strip().lower().replace("\xa0", " ")
    if not text:
        return 0

    # Prefer explicit numeric quantity from free text, e.g. "в наличии 12 шт".
    match = re.search(r"(-?\d+([.,]\d+)?)", text)
    if match:
        token = match.group(1).replace(",", ".")
        try:
            return max(0, int(float(token)))
        except Exception:
            pass

    status = classify_availability(text)
    if status == "in_stock":
        # If supplier says "в наличии/есть" with no number, assume practical stock.
        return 10
    return 0
