"""Helpers for product attachment normalization and persistence."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.input_validation import validate_public_manual_url
from models import ProductAttachment


def _normalize_url(value: Any) -> str:
    try:
        return validate_public_manual_url(str(value or ""))
    except ValueError:
        return ""


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
) -> bool:
    """Replace manual rows and report whether their public state changed."""

    normalized = normalize_manuals(manuals)
    existing = list(
        (
            await session.execute(
                select(ProductAttachment).where(
                    ProductAttachment.product_id == product_id,
                    ProductAttachment.kind == "manual",
                )
            )
        ).scalars().all()
    )
    existing_state = sorted(
        (
            row.kind,
            row.title,
            row.url,
            row.source or "",
        )
        for row in existing
    )
    requested_state = sorted(
        (
            item["kind"],
            item["title"],
            item["url"],
            item["source"],
        )
        for item in normalized
    )
    if existing_state == requested_state:
        return False

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
    return True


async def list_manuals(session: AsyncSession, *, product_id: int) -> List[ProductAttachment]:
    rows = await session.execute(
        select(ProductAttachment).where(
            ProductAttachment.product_id == product_id,
            ProductAttachment.kind == "manual",
        )
    )
    return list(rows.scalars().all())
