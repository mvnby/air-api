from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.product import Product
from models.supplier import SupplierOffer, SupplierPriceSource
from services.product_manager_service import ProductManagerService
from services.supplier_source_url import normalize_source_url, source_url_variants


MATCH_NORMALIZER_VERSION = "supplier-match-v2"

_PARASITE_PATTERNS = [
    r"\bсплит[-\s]*система\b",
    r"\bвнутренний\s+блок\b",
    r"\bнаружный\s+блок\b",
    r"\bмобильный\s+кондиционер\b",
    r"\bкондиционер\b",
]

_INDOOR_MARKERS = ("внутрен", "indoor", "внутр.")
_OUTDOOR_MARKERS = ("наруж", "outdoor", "внешн.")
_CAPACITY_MARKERS = {"07", "09", "12", "18", "24", "25", "28", "30", "35", "36", "48", "50", "55", "60", "70"}
_MODEL_TOKEN_RE = re.compile(r"(?<![A-Z0-9])(?=[A-Z0-9/-]*\d)(?=[A-Z0-9/-]*[A-Z])[A-Z0-9]{1,12}(?:[-/][A-Z0-9]{1,12})+(?![A-Z0-9])|(?<![A-Z0-9])(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])(?:[A-Z]{1,5}|[0-9][A-Z])[A-Z0-9]{3,16}(?![A-Z0-9])")
_OPTIONAL_SUFFIX_MODEL_RE = re.compile(
    r"(?<![A-Z0-9])(?P<base>(?=[A-Z0-9/-]*\d)(?=[A-Z0-9/-]*[A-Z])[A-Z0-9]{1,12}(?:[-/][A-Z0-9]{1,12})+)\((?P<suffix>-[A-Z0-9]{1,8})\)"
)
_CYRILLIC_LOOKALIKES = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "У": "Y",
        "Х": "X",
        "а": "A",
        "в": "B",
        "е": "E",
        "к": "K",
        "м": "M",
        "н": "H",
        "о": "O",
        "р": "P",
        "с": "C",
        "т": "T",
        "у": "Y",
        "х": "X",
    }
)


@dataclass(frozen=True)
class MatchProfile:
    title_normalized: str
    model_tokens: list[str]
    indoor_model_tokens: list[str]
    outdoor_model_tokens: list[str]


def normalize_offer_title_for_search(title_raw: str | None) -> str:
    value = _normalize_text(title_raw)
    for pattern in _PARASITE_PATTERNS:
        value = re.sub(pattern, " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip()
    return value or (title_raw or "").strip()


def build_offer_match_profile(title_raw: str | None) -> MatchProfile:
    normalized = normalize_offer_title_for_search(title_raw)
    token_profile = _extract_model_tokens(title_raw or "")
    return MatchProfile(
        title_normalized=normalized,
        model_tokens=token_profile["model_tokens"],
        indoor_model_tokens=token_profile["indoor_model_tokens"],
        outdoor_model_tokens=token_profile["outdoor_model_tokens"],
    )


def supplier_offer_match_payload(title_raw: str | None) -> dict[str, Any]:
    profile = build_offer_match_profile(title_raw)
    return {
        "title_normalized": profile.title_normalized,
        "model_tokens": profile.model_tokens,
        "indoor_model_tokens": profile.indoor_model_tokens,
        "outdoor_model_tokens": profile.outdoor_model_tokens,
        "match_normalizer_version": MATCH_NORMALIZER_VERSION,
    }


def build_product_match_profile(product: dict[str, Any]) -> MatchProfile:
    specs = product.get("specs") if isinstance(product.get("specs"), dict) else {}
    raw_parts = [
        product.get("title"),
        _first_spec_value(specs, ("model_indoor", "Модель внутреннего блока", "UNIT_INDOOR")),
        _first_spec_value(specs, ("model_outdoor", "Модель наружного блока", "UNIT_OUTDOOR")),
    ]
    title_profile = _extract_model_tokens(" ".join(str(part or "") for part in raw_parts))
    indoor_tokens = _extract_model_tokens(str(raw_parts[1] or ""))["model_tokens"]
    outdoor_tokens = _extract_model_tokens(str(raw_parts[2] or ""))["model_tokens"]
    return MatchProfile(
        title_normalized=normalize_offer_title_for_search(product.get("title")),
        model_tokens=_dedupe([*title_profile["model_tokens"], *indoor_tokens, *outdoor_tokens]),
        indoor_model_tokens=_dedupe([*title_profile["indoor_model_tokens"], *indoor_tokens]),
        outdoor_model_tokens=_dedupe([*title_profile["outdoor_model_tokens"], *outdoor_tokens]),
    )


async def suggest_products_for_offer(
    session: AsyncSession,
    *,
    title_raw: str | None,
    offer: SupplierOffer | None = None,
    offer_source_name: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    offer_profile = _profile_from_offer_or_title(offer, title_raw)
    offer_source_url = normalize_source_url(offer.source_url if offer else None)
    if offer_source_name is None and offer and offer.source_id:
        source = await session.get(SupplierPriceSource, offer.source_id)
        offer_source_name = source.sheet_name if source else None
    offer_catalog_categories = _infer_offer_catalog_categories(
        source_name=offer_source_name,
        title_raw=offer.title_raw if offer else title_raw,
    )
    if not offer_profile.title_normalized and not offer_profile.model_tokens and not offer_source_url:
        return {
            "normalized_query": "",
            "offer_tokens": [],
            "indoor_model_tokens": [],
            "outdoor_model_tokens": [],
            "candidates": [],
            "auto_eligible": False,
            "reason": "empty_query",
        }

    candidate_rows = await _collect_candidate_products(
        session,
        offer_profile,
        offer_source_url=offer_source_url,
        limit=max(limit * 3, 12),
    )
    scored = [
        _score_candidate(
            offer_profile=offer_profile,
            product=item,
            offer_source_url=offer_source_url,
            offer_catalog_categories=offer_catalog_categories,
            offer_rrc=_decimal_to_float(offer.rrc_byn) if offer else None,
        )
        for item in candidate_rows
    ]
    scored.sort(key=lambda item: (-item["score"], item["title"].casefold(), item["product_id"]))
    candidates = scored[:limit]
    reason, auto_eligible = _suggestion_status(candidates)
    return {
        "normalized_query": offer_profile.title_normalized,
        "offer_tokens": offer_profile.model_tokens,
        "indoor_model_tokens": offer_profile.indoor_model_tokens,
        "outdoor_model_tokens": offer_profile.outdoor_model_tokens,
        "candidates": candidates,
        "auto_eligible": auto_eligible,
        "reason": reason,
    }


def _profile_from_offer_or_title(offer: SupplierOffer | None, title_raw: str | None) -> MatchProfile:
    if offer and offer.match_normalizer_version == MATCH_NORMALIZER_VERSION:
        return MatchProfile(
            title_normalized=offer.title_normalized or normalize_offer_title_for_search(offer.title_raw),
            model_tokens=_normalize_token_list(offer.model_tokens),
            indoor_model_tokens=_normalize_token_list(offer.indoor_model_tokens),
            outdoor_model_tokens=_normalize_token_list(offer.outdoor_model_tokens),
        )
    return build_offer_match_profile(offer.title_raw if offer else title_raw)


async def _collect_candidate_products(
    session: AsyncSession,
    offer_profile: MatchProfile,
    *,
    offer_source_url: str | None = None,
    limit: int,
) -> list[dict[str, Any]]:
    queries = _dedupe([
        offer_profile.title_normalized,
        *offer_profile.model_tokens[:6],
        *[" ".join(offer_profile.model_tokens[:2]) if len(offer_profile.model_tokens) >= 2 else ""],
    ])
    by_id: dict[int, dict[str, Any]] = {}
    if offer_source_url:
        result = await session.execute(
            select(Product).where(Product.source_url.in_(source_url_variants(offer_source_url))).limit(limit)
        )
        for product in result.scalars().all():
            if product.id is not None:
                by_id[int(product.id)] = _product_to_candidate_dict(product)
    for query in queries:
        if not query:
            continue
        result = await ProductManagerService.smart_search(session=session, q=query, limit=limit)
        for item in result.get("items", []):
            product_id = item.get("id")
            if product_id is None:
                continue
            by_id[int(product_id)] = item
    return list(by_id.values())


def _score_candidate(
    *,
    offer_profile: MatchProfile,
    product: dict[str, Any],
    offer_source_url: str | None = None,
    offer_catalog_categories: set[str] | None = None,
    offer_rrc: float | None = None,
) -> dict[str, Any]:
    product_profile = build_product_match_profile(product)
    offer_tokens = set(offer_profile.model_tokens)
    product_tokens = set(product_profile.model_tokens)
    matched_tokens = sorted(offer_tokens & product_tokens)
    missing_tokens = sorted(offer_tokens - product_tokens)
    indoor_matches = sorted(set(offer_profile.indoor_model_tokens) & set(product_profile.indoor_model_tokens))
    outdoor_matches = sorted(set(offer_profile.outdoor_model_tokens) & set(product_profile.outdoor_model_tokens))
    cross_indoor = sorted(set(offer_profile.indoor_model_tokens) & set(product_profile.outdoor_model_tokens))
    cross_outdoor = sorted(set(offer_profile.outdoor_model_tokens) & set(product_profile.indoor_model_tokens))

    score = 0
    breakdown: dict[str, int] = {}
    explanations: list[str] = []

    product_source_url = normalize_source_url(product.get("source_url"))
    if offer_source_url and product_source_url and offer_source_url == product_source_url:
        score += 120
        breakdown["source_url"] = 120
        explanations.append("Совпала ссылка источника / Onliner")

    if matched_tokens:
        value = min(85, 42 * len(matched_tokens))
        score += value
        breakdown["model_token"] = value
        explanations.append(f"Совпали модели: {', '.join(matched_tokens[:4])}")
    if indoor_matches:
        score += 24
        breakdown["indoor_token"] = 24
        explanations.append(f"Внутренний блок: {', '.join(indoor_matches[:3])}")
    if outdoor_matches:
        score += 24
        breakdown["outdoor_token"] = 24
        explanations.append(f"Наружный блок: {', '.join(outdoor_matches[:3])}")
    if cross_indoor or cross_outdoor:
        score -= 45
        breakdown["role_mismatch"] = -45
        explanations.append("Есть риск перепутать внутренний и наружный блок")

    product_catalog = _product_catalog_category(product)
    if offer_catalog_categories and product_catalog:
        catalog_label = _catalog_label(product_catalog)
        if product_catalog in offer_catalog_categories:
            score += 18
            breakdown["catalog_context"] = 18
            explanations.append(f"Контекст прайса совпал: {catalog_label}")
            if _has_explicit_catalog(product):
                score += 6
                breakdown["catalog_source"] = 6
                explanations.append("Товар из нормализованного каталога производителя")
        elif _catalogs_are_incompatible(offer_catalog_categories, product_catalog):
            score -= 34
            breakdown["catalog_mismatch"] = -34
            explanations.append(f"Категория прайса не похожа на товар: {catalog_label}")

    offer_capacity = _capacity_markers_from_tokens(offer_profile.model_tokens)
    product_capacity = _capacity_markers_from_tokens(product_profile.model_tokens)
    if offer_capacity and product_capacity:
        common_capacity = sorted(offer_capacity & product_capacity)
        if common_capacity:
            score += 10
            breakdown["capacity"] = 10
            explanations.append(f"Совпал индекс мощности: {', '.join(common_capacity[:3])}")
        else:
            score -= 10
            breakdown["capacity_mismatch"] = -10
            explanations.append("Индекс мощности отличается")

    if offer_rrc:
        product_price = _decimal_to_float(product.get("price"))
        if product_price and product_price > 0:
            delta = abs(product_price - offer_rrc) / max(product_price, offer_rrc)
            if delta <= 0.2:
                score += 6
                breakdown["price_close"] = 6
                explanations.append("Цена близка к РРЦ поставщика")
            elif delta >= 0.5:
                score -= 8
                breakdown["price_far"] = -8
                explanations.append("Цена заметно отличается от РРЦ поставщика")

    if not explanations:
        explanations.append("Подобрано только текстовым поиском")

    confidence = max(0, min(100, score))
    return {
        "product_id": product["id"],
        "title": product["title"],
        "price": product["price"],
        "source_url": product.get("source_url"),
        "score": score,
        "confidence": confidence,
        "matched_tokens": matched_tokens,
        "missing_tokens": missing_tokens,
        "explanations": explanations,
        "score_breakdown": breakdown,
    }


def _product_to_candidate_dict(product: Product) -> dict[str, Any]:
    return {
        "id": product.id,
        "title": product.title,
        "price": product.price,
        "source_url": product.source_url,
        "specs": product.specs or {},
    }


def _suggestion_status(candidates: list[dict[str, Any]]) -> tuple[str, bool]:
    if not candidates:
        return "no_candidates", False
    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    top_score = int(top.get("score") or 0)
    second_score = int(second.get("score") or 0) if second else 0
    if top_score >= 75 and (second is None or top_score - second_score >= 15):
        return "high_score", True
    if second and top_score - second_score < 15:
        return "ambiguous", False
    return "low_confidence", False


def _extract_model_tokens(raw: str) -> dict[str, list[str]]:
    text = _normalize_token_text(raw)
    optional_text = _normalize_token_text_with_parentheses(raw)
    model_tokens: list[str] = []
    indoor_tokens: list[str] = []
    outdoor_tokens: list[str] = []

    def append_token(token: str, *, has_indoor_context: bool, has_outdoor_context: bool) -> None:
        if not _looks_like_model_token(token):
            return
        model_tokens.append(token)
        if has_indoor_context or token.startswith(("MDS", "AS", "HSU", "RC", "RCI", "MDC", "MDF")):
            indoor_tokens.append(token)
        if has_outdoor_context or token.startswith(
            ("MDO", "1U", "UU", "CU", "MD2O", "MD3O", "MD4O", "MD5O", "AMW", "AUW")
        ):
            outdoor_tokens.append(token)

    for match in _OPTIONAL_SUFFIX_MODEL_RE.finditer(optional_text):
        has_indoor_context, has_outdoor_context = _role_context(optional_text, match.start(), match.end())
        append_token(
            _normalize_model_token(f"{match.group('base')}{match.group('suffix')}"),
            has_indoor_context=has_indoor_context,
            has_outdoor_context=has_outdoor_context,
        )

    for match in _MODEL_TOKEN_RE.finditer(text):
        has_indoor_context, has_outdoor_context = _role_context(text, match.start(), match.end())
        raw_token = str(match.group(0))
        token_candidates = [_normalize_model_token(raw_token)]
        if "/" in raw_token:
            token_candidates.extend(_normalize_model_token(part) for part in raw_token.split("/"))
        for token in token_candidates:
            append_token(
                token,
                has_indoor_context=has_indoor_context,
                has_outdoor_context=has_outdoor_context,
            )
    return {
        "model_tokens": _dedupe(model_tokens),
        "indoor_model_tokens": _dedupe(indoor_tokens),
        "outdoor_model_tokens": _dedupe(outdoor_tokens),
    }


def _normalize_text(raw: str | None) -> str:
    value = (raw or "").lower().replace("\xa0", " ")
    value = re.sub(r"[^0-9a-zA-Zа-яА-ЯёЁ\-+/ .]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _normalize_token_text(raw: str | None) -> str:
    value = (raw or "").replace("\xa0", " ").translate(_CYRILLIC_LOOKALIKES).upper()
    value = value.replace("–", "-").replace("—", "-").replace("_", "-")
    value = re.sub(r"[^0-9A-Zа-яА-ЯёЁ\-+/ .]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _normalize_token_text_with_parentheses(raw: str | None) -> str:
    value = (raw or "").replace("\xa0", " ").translate(_CYRILLIC_LOOKALIKES).upper()
    value = value.replace("–", "-").replace("—", "-").replace("_", "-")
    value = re.sub(r"[^0-9A-Zа-яА-ЯёЁ\-+/ ().]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _normalize_model_token(raw: str) -> str:
    token = raw.translate(_CYRILLIC_LOOKALIKES).upper().strip(" ,.;:")
    token = token.replace(" ", "").replace("_", "-").replace("–", "-").replace("—", "-")
    token = re.sub(r"-{2,}", "-", token)
    return token.strip("-/")


def _normalize_token_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return _dedupe(_normalize_model_token(str(value or "")) for value in values)


def _looks_like_model_token(token: str) -> bool:
    if len(token) < 4 or len(token) > 32:
        return False
    if not re.search(r"[A-Z]", token) or not re.search(r"\d", token):
        return False
    if token in {"E-POS", "E-MAIL", "YCJ-A002"}:
        return False
    return True


def _capacity_markers_from_tokens(tokens: Iterable[str]) -> set[str]:
    markers: set[str] = set()
    for token in tokens:
        for value in re.findall(r"\d{2}", token):
            if value in _CAPACITY_MARKERS:
                markers.add(value)
    return markers


def _role_context(text: str, start: int, end: int) -> tuple[bool, bool]:
    left = max(text.rfind(delimiter, 0, start) for delimiter in ("+", "/", ",", ";"))
    right_candidates = [text.find(delimiter, end) for delimiter in ("+", "/", ",", ";")]
    right_values = [value for value in right_candidates if value >= 0]
    right = min(right_values) if right_values else len(text)
    segment = text[left + 1:right].lower()
    has_indoor_context = any(marker in segment for marker in _INDOOR_MARKERS)
    has_outdoor_context = any(marker in segment for marker in _OUTDOOR_MARKERS)
    return has_indoor_context, has_outdoor_context


def _infer_offer_catalog_categories(*, source_name: str | None, title_raw: str | None) -> set[str]:
    source = _normalize_text(source_name)
    title = _normalize_text(title_raw)
    combined = f"{source} {title}"

    if "pac" in source or "pack" in source or "полупром" in combined:
        return {"semi"}
    if any(marker in combined for marker in ("кассет", "каналь", "колонн", "напольно", "потолоч", "консол")):
        return {"semi"}
    if "atom" in source or "vrf" in combined or "мультизон" in combined:
        return {"vrf"}
    if "multi" in source or "мульти" in combined:
        return {"multi"}
    if "rac" in source:
        component_only = (
            any(marker in title for marker in _INDOOR_MARKERS + _OUTDOOR_MARKERS)
            and "сплит" not in title
            and "система" not in title
        )
        return {"multi"} if component_only else {"household"}
    return set()


def _product_catalog_category(product: dict[str, Any]) -> str | None:
    specs = product.get("specs") if isinstance(product.get("specs"), dict) else {}
    explicit = str(
        specs.get("__mdv_catalog")
        or specs.get("mdv_catalog")
        or specs.get("__hisense_catalog")
        or specs.get("hisense_catalog")
        or ""
    ).strip().lower()
    if explicit in {"household", "semi", "multi"}:
        return explicit

    system_type = _normalize_text(specs.get("type") or specs.get("Тип"))
    indoor_type = _normalize_text(specs.get("indoor_type") or specs.get("Тип внутреннего блока"))
    title = _normalize_text(product.get("title"))
    combined = f"{system_type} {indoor_type} {title}"

    if "мульти" in combined:
        return "multi"
    if any(marker in system_type for marker in _INDOOR_MARKERS + _OUTDOOR_MARKERS):
        return "multi"
    component_title = (
        "блок" in title
        and any(marker in title for marker in _INDOOR_MARKERS + _OUTDOOR_MARKERS)
        and "сплит" not in title
        and "система" not in title
    )
    if component_title:
        return "multi"
    if "полупром" in combined or any(
        marker in combined for marker in ("кассет", "каналь", "колонн", "напольно", "потолоч")
    ):
        return "semi"
    if "сплит" in system_type:
        return "household"
    return None


def _has_explicit_catalog(product: dict[str, Any]) -> bool:
    specs = product.get("specs") if isinstance(product.get("specs"), dict) else {}
    return bool(
        specs.get("__mdv_catalog")
        or specs.get("mdv_catalog")
        or specs.get("__hisense_catalog")
        or specs.get("hisense_catalog")
    )


def _catalogs_are_incompatible(offer_categories: set[str], product_catalog: str) -> bool:
    if "vrf" in offer_categories or product_catalog == "vrf":
        return product_catalog not in offer_categories
    known = {"household", "semi", "multi"}
    return bool(offer_categories & known) and product_catalog in known


def _catalog_label(catalog: str) -> str:
    return {
        "household": "бытовая сплит-система",
        "semi": "полупром",
        "multi": "мультисплит",
        "vrf": "VRF/ATOM",
    }.get(catalog, catalog)


def _first_spec_value(specs: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = specs.get(key)
        if value:
            return str(value)
    return ""


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, Decimal):
            return float(value)
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out
