"""Client-facing order-line descriptions kept separate from catalog identity."""

from __future__ import annotations

from typing import Any

MAX_CLIENT_DESCRIPTION_LENGTH = 2_000


def normalize_client_description(value: Any) -> str | None:
    if value is None:
        return None
    lines = [
        line.strip()
        for line in str(value)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .split("\n")
    ]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    normalized = "\n".join(lines)
    if len(normalized) > MAX_CLIENT_DESCRIPTION_LENGTH:
        raise ValueError(
            f"client description must not exceed {MAX_CLIENT_DESCRIPTION_LENGTH} characters"
        )
    return normalized or None


def product_line_document_title(link: Any, fallback: str = "Товар") -> str:
    identity = str(
        getattr(link, "title_snapshot", None)
        or getattr(getattr(link, "product", None), "title", "")
        or fallback
    ).strip() or fallback
    description = normalize_client_description(
        getattr(link, "client_description", None)
    )
    return f"{identity}\n{description}" if description else identity
