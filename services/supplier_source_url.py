from __future__ import annotations

import re
from collections.abc import Iterable


_URL_RE = re.compile(r"https?://[^\s<>'\"()]+", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:!?)]}"


def normalize_source_url(raw: str | None) -> str | None:
    value = (raw or "").replace("\xa0", " ").strip()
    if not value:
        return None
    match = _URL_RE.search(value)
    if not match:
        return None
    return match.group(0).strip(_TRAILING_PUNCTUATION).rstrip("/")


def source_url_variants(raw: str | None) -> list[str]:
    normalized = normalize_source_url(raw)
    if not normalized:
        return []
    variants = [normalized]
    with_slash = f"{normalized}/"
    if with_slash not in variants:
        variants.append(with_slash)
    return variants


def extract_first_source_url(values: Iterable[object]) -> str | None:
    for value in values:
        source_url = normalize_source_url(str(value or ""))
        if source_url:
            return source_url
    return None
