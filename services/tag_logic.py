from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from slugify import slugify


CATEGORY_TAG_TITLES: Dict[str, str] = {
    "cat-household": "Бытовые",
    "cat-multi": "Мульти-сплит",
    "cat-industrial": "Полупромышленные",
}

_TITLE_SKIP_TOKENS = {
    "кондиционер",
    "сплит",
    "система",
    "сплит-система",
    "мульти-сплит",
    "мульти",
    "инверторный",
    "инверторная",
    "настенный",
    "внутренний",
    "наружный",
    "блок",
    "комплект",
    "бытовой",
    "бытовые",
    "полупромышленный",
    "полупромышленные",
}


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalized(value: Any) -> str:
    return _to_text(value).lower().replace("ё", "е")


def _first_existing(specs: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in specs:
            return specs.get(key)

    lowered = {
        str(key).strip().lower(): value
        for key, value in specs.items()
        if isinstance(key, str)
    }
    for key in keys:
        value = lowered.get(str(key).strip().lower())
        if value is not None:
            return value
    return None


def _parse_min_temp_heating(metrics: Optional[Dict[str, Any]], specs: Dict[str, Any]) -> Optional[int]:
    raw = (metrics or {}).get("min_temp_heating")
    if raw is None:
        raw = _first_existing(specs, ("temp_range_heat", "Рабочая температура при обогреве"))
    if raw is None:
        return None

    text = _to_text(raw).replace("−", "-").replace("—", "-")
    matches = re.findall(r"-\d+(?:[.,]\d+)?", text)
    if not matches:
        return None

    parsed: List[int] = []
    for token in matches:
        try:
            parsed.append(int(float(token.replace(",", "."))))
        except ValueError:
            continue
    return min(parsed) if parsed else None


def _extract_brand_from_title(title: str) -> Optional[str]:
    if not title:
        return None
    for raw_token in title.split():
        token = raw_token.strip("()[]{}.,;:!?'\"`")
        if not token:
            continue
        if token.lower() in _TITLE_SKIP_TOKENS:
            continue
        if not re.search(r"[a-zа-я]", token, flags=re.IGNORECASE):
            continue
        return token
    return None


def extract_brand_name(specs: Optional[Dict[str, Any]] = None, title: str = "") -> Optional[str]:
    specs = specs or {}
    raw_brand = _first_existing(
        specs,
        ("Бренд", "brand", "Марка", "Производитель", "manufacturer"),
    )
    if raw_brand:
        primary = re.split(r"[,/|;]", _to_text(raw_brand), maxsplit=1)[0].strip()
        if primary:
            token = primary.split()[0]
            if token:
                return token

    return _extract_brand_from_title(title)


def extract_brand_slug(specs: Optional[Dict[str, Any]] = None, title: str = "") -> Optional[str]:
    brand_name = extract_brand_name(specs=specs, title=title)
    if not brand_name:
        return None
    slug = slugify(brand_name, lowercase=True)
    return slug or None


def detect_category_slug(
    metrics: Optional[Dict[str, Any]] = None,
    specs: Optional[Dict[str, Any]] = None,
    title: str = "",
) -> Optional[str]:
    specs = specs or {}
    indoor_type = _normalized(_first_existing(specs, ("indoor_type", "Тип внутреннего блока")))
    system_type = _normalized(_first_existing(specs, ("type", "Тип кондиционера", "Тип")))
    title_text = _normalized(title)

    combined_type = " ".join((indoor_type, system_type, title_text))

    multi_markers = (
        "мульти",
        "multi",
        "внутренний блок",
        "наружный блок",
        "indoor block",
        "outdoor block",
    )
    if any(marker in combined_type for marker in multi_markers):
        return "cat-multi"

    industrial_markers = (
        "кассет",
        "каналь",
        "воздуховод",
        "подпотолоч",
        "потолоч",
        "напольно",
        "floor-ceiling",
        "floor ceiling",
        "колонн",
        "console",
    )
    if any(marker in combined_type for marker in industrial_markers):
        return "cat-industrial"

    if "настенн" in combined_type:
        return "cat-household"

    if any(marker in combined_type for marker in ("сплит", "split")):
        return "cat-household"

    return None


def get_auto_tags(metrics: Dict[str, Any], specs: Optional[Dict[str, Any]] = None, title: str = "") -> List[str]:
    """
    Returns automatic TAG SLUGS inferred from parsed metrics/specs/title.
    Supported automatic tags:
    - winter-* tiers
    - indoor unit type (wall/ceiling/duct/cassette)
    - catalog category (cat-household/cat-multi/cat-industrial)
    - brand slug (from specs["Бренд"]/specs["brand"] or title fallback)
    """
    specs = specs or {}
    tags: List[str] = []

    min_temp = _parse_min_temp_heating(metrics, specs)
    if min_temp is not None and min_temp <= -15:
        if min_temp <= -30:
            tags.append("winter-30")
        elif min_temp <= -25:
            tags.append("winter-25")
        elif min_temp <= -20:
            tags.append("winter-20")
        else:
            tags.append("winter-15")

    unit_type = _normalized(_first_existing(specs, ("Тип внутреннего блока", "indoor_type")))
    if "настенн" in unit_type:
        tags.append("wall")
    elif "подпотолоч" in unit_type or "потолоч" in unit_type:
        tags.append("ceiling")
    elif "каналь" in unit_type:
        tags.append("duct")
    elif "кассет" in unit_type:
        tags.append("cassette")

    category_slug = detect_category_slug(metrics=metrics, specs=specs, title=title)
    if category_slug:
        tags.append(category_slug)

    brand_slug = extract_brand_slug(specs=specs, title=title)
    if brand_slug:
        tags.append(brand_slug)

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(tags))
