from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from services.product_manager_service import ProductManagerService

_PARASITE_PATTERNS = [
    r"\bсплит[-\s]*система\b",
    r"\bвнутренний\s+блок\b",
    r"\bнаружный\s+блок\b",
    r"\bмобильный\s+кондиционер\b",
    r"\bкондиционер\b",
]


def normalize_offer_title_for_search(title_raw: str | None) -> str:
    value = (title_raw or "").lower()
    for pattern in _PARASITE_PATTERNS:
        value = re.sub(pattern, " ", value, flags=re.IGNORECASE)
    value = re.sub(r"[^0-9a-zA-Zа-яА-ЯёЁ\-+/ ]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or (title_raw or "").strip()


async def suggest_products_for_offer(
    session: AsyncSession,
    *,
    title_raw: str | None,
    limit: int = 5,
) -> dict[str, Any]:
    normalized_query = normalize_offer_title_for_search(title_raw)
    if not normalized_query:
        return {
            "normalized_query": "",
            "candidates": [],
            "auto_eligible": False,
            "reason": "empty_query",
        }

    result = await ProductManagerService.smart_search(session=session, q=normalized_query, limit=limit)
    items = result.get("items", [])
    candidates = [{"product_id": i["id"], "title": i["title"], "price": i["price"]} for i in items]
    if len(candidates) == 1:
        reason = "single_exact"
    elif len(candidates) > 1:
        reason = "multiple_candidates"
    else:
        reason = "no_candidates"
    return {
        "normalized_query": normalized_query,
        "candidates": candidates,
        "auto_eligible": len(candidates) == 1,
        "reason": reason,
    }
