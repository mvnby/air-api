"""Helpers for product attachment normalization and persistence."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ProductAttachment


def _normalize_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    if not parts.scheme and not parts.netloc:
        return raw
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def normalize_manuals(raw_manuals: Iterable[Dict[str, Any]] | None) -> List[Dict[str, str]]:
    """Normalize parser/UI manuals payload into deduplicated canonical rows."""
    if not raw_manuals:
        return []

    result: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for raw in raw_manuals:
        if not isinstance(raw, dict):
            continue

        url = _normalize_url(raw.get("url") or raw.get("href"))
        if not url:
            continue

        title = str(raw.get("title") or "Инструкция").strip() or "Инструкция"
        kind = str(raw.get("kind") or "manual").strip().lower() or "manual"
        source = str(raw.get("source") or "").strip()

        key = (kind, url)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "kind": kind,
                "title": title,
                "url": url,
                "source": source,
            }
        )

    return result


async def replace_manuals(
    session: AsyncSession,
    *,
    product_id: int,
    manuals: Iterable[Dict[str, Any]] | None,
) -> None:
    normalized = normalize_manuals(manuals)
    await session.execute(
        delete(ProductAttachment).where(
            ProductAttachment.product_id == product_id,
            ProductAttachment.kind == "manual",
        )
    )
    for item in normalized:
        session.add(
            ProductAttachment(
                product_id=product_id,
                kind=item["kind"],
                title=item["title"],
                url=item["url"],
                source=item["source"] or None,
            )
        )


async def list_manuals(session: AsyncSession, *, product_id: int) -> List[ProductAttachment]:
    rows = await session.execute(
        select(ProductAttachment).where(
            ProductAttachment.product_id == product_id,
            ProductAttachment.kind == "manual",
        )
    )
    return list(rows.scalars().all())
