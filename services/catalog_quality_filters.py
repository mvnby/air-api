from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from models.product import Product


EQUIPMENT_TYPE_LABELS = {
    "cat-household": "Бытовые сплит-системы",
    "cat-multi": "Мульти-сплит",
    "cat-industrial": "Полупромышленное",
}

TYPE_TAG_LABELS = {
    "wall": "Настенные",
    "cassette": "Кассетные",
    "duct": "Канальные",
    "ceiling": "Напольно-потолочные",
    "column": "Колонные",
}

INDOOR_TYPE_SLUGS = {
    "настенный": "wall",
    "кассетный": "cassette",
    "канальный": "duct",
    "напольно-потолочный": "ceiling",
    "потолочный": "ceiling",
    "floor_ceiling": "ceiling",
    "floor-ceiling": "ceiling",
    "колонный": "column",
}

MULTI_COMPONENT_LABELS = {
    "multi-indoor": "Внутренние блоки",
    "multi-outdoor": "Наружные блоки",
    "multi-kit": "Комплекты",
}

FIXABLE_CATEGORIES = {"media", "identity", "specs"}


def _clean(value: Any) -> str:
    return str(value or "").strip().lower().replace("ё", "е")


def classify_product(product: Product) -> tuple[str | None, str | None, str | None, str | None]:
    """Return normalized equipment type and subtype without title heuristics."""
    category_slug: str | None = None
    category_label: str | None = None
    type_slug: str | None = None
    type_label: str | None = None
    for tag in product.tags or []:
        group_slug = tag.group.slug if tag.group else None
        if group_slug == "category" and tag.slug in EQUIPMENT_TYPE_LABELS:
            category_slug = tag.slug
            category_label = EQUIPMENT_TYPE_LABELS[tag.slug]
        elif group_slug == "type" and tag.slug in TYPE_TAG_LABELS:
            type_slug = tag.slug
            type_label = TYPE_TAG_LABELS[tag.slug]

    specs = product.specs or {}
    if category_slug == "cat-industrial":
        normalized_indoor_type = _clean(specs.get("indoor_type"))
        normalized_slug = INDOOR_TYPE_SLUGS.get(normalized_indoor_type)
        if normalized_slug:
            type_slug = normalized_slug
            type_label = TYPE_TAG_LABELS[normalized_slug]
    elif category_slug == "cat-multi":
        normalized_type = _clean(specs.get("type"))
        normalized_indoor_type = _clean(specs.get("indoor_type"))
        normalized_indoor_slug = INDOOR_TYPE_SLUGS.get(normalized_indoor_type)
        has_indoor_component = bool(specs.get("includes_indoor_unit")) or any(
            specs.get(key) not in (None, "", False)
            for key in ("width_indoor", "height_indoor", "depth_indoor")
        )
        has_outdoor_component = bool(specs.get("includes_outdoor_unit")) or any(
            specs.get(key) not in (None, "", False)
            for key in ("width_outdoor", "height_outdoor", "depth_outdoor")
        )
        if normalized_type == "внутренний блок":
            type_slug, type_label = "multi-indoor", MULTI_COMPONENT_LABELS["multi-indoor"]
        elif normalized_type == "наружный блок":
            type_slug, type_label = "multi-outdoor", MULTI_COMPONENT_LABELS["multi-outdoor"]
        elif type_slug in TYPE_TAG_LABELS or normalized_indoor_slug or (has_indoor_component and not has_outdoor_component):
            type_slug, type_label = "multi-indoor", MULTI_COMPONENT_LABELS["multi-indoor"]
        elif has_outdoor_component and not has_indoor_component:
            type_slug, type_label = "multi-outdoor", MULTI_COMPONENT_LABELS["multi-outdoor"]
        elif has_indoor_component and has_outdoor_component:
            type_slug, type_label = "multi-kit", MULTI_COMPONENT_LABELS["multi-kit"]
        else:
            type_slug, type_label = None, None

    return category_slug, category_label, type_slug, type_label


def enrich_work_priority(row: dict[str, Any]) -> None:
    issues = row.get("issues") or []
    fixable = [issue for issue in issues if issue.get("category") in FIXABLE_CATEGORIES]
    critical_fixable = [issue for issue in fixable if issue.get("severity") == "critical"]
    published = bool(row.get("is_published"))
    in_stock = int(row.get("available_qty") or 0) > 0
    score_gap = max(0, 100 - int(row.get("score") or 0))

    priority_score = len(critical_fixable) * 100 + len(fixable) * 20 + score_gap
    if published:
        priority_score += 30
    if in_stock:
        priority_score += 30

    if published and in_stock and critical_fixable:
        priority = "high"
        reason = "На сайте · в наличии · критичная проблема контента"
    elif published and in_stock and fixable:
        priority = "medium"
        reason = "На сайте · в наличии · есть исправимые замечания"
    else:
        priority = "low"
        if not published:
            reason = "Товар скрыт с сайта"
        elif not in_stock:
            reason = "Нет доступного наличия"
        else:
            reason = "Нет срочных исправимых замечаний"

    row["fixable_issue_count"] = len(fixable)
    row["work_priority"] = priority
    row["work_priority_score"] = priority_score
    row["priority_reason"] = reason


def filter_dimension_rows(
    rows: list[dict[str, Any]],
    *,
    equipment_type: str | None = None,
    equipment_subtype: str | None = None,
    brand_id: int | None = None,
    series_id: int | None = None,
    series_state: str | None = None,
    supplier_id: int | None = None,
    supplier_state: str | None = None,
    publication: str | None = None,
    availability: str | None = None,
    priority: str | None = None,
    score_min: int | None = None,
    score_max: int | None = None,
    only_fixable: bool = False,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        suppliers = row.get("suppliers") or []
        selected_suppliers = [item for item in suppliers if not supplier_id or item.get("supplier_id") == supplier_id]
        distinct_supplier_ids = {item.get("supplier_id") for item in suppliers if item.get("supplier_id")}
        if equipment_type and row.get("equipment_type") != equipment_type:
            continue
        if equipment_subtype and row.get("equipment_subtype") != equipment_subtype:
            continue
        if brand_id and row.get("brand_id") != brand_id:
            continue
        if series_id and row.get("series_id") != series_id:
            continue
        if series_state == "missing" and row.get("series_id"):
            continue
        if series_state == "assigned" and not row.get("series_id"):
            continue
        if supplier_id and not selected_suppliers:
            continue
        if supplier_state == "mapped" and not selected_suppliers:
            continue
        if supplier_state == "in_stock" and not any(int(item.get("qty") or 0) > 0 for item in selected_suppliers):
            continue
        if supplier_state == "unmapped" and suppliers:
            continue
        if supplier_state == "multiple" and len(distinct_supplier_ids) <= 1:
            continue
        if publication == "published" and not row.get("is_published"):
            continue
        if publication == "hidden" and row.get("is_published"):
            continue
        if availability == "in_stock" and int(row.get("available_qty") or 0) <= 0:
            continue
        if availability == "out_of_stock" and int(row.get("available_qty") or 0) > 0:
            continue
        if priority and row.get("work_priority") != priority:
            continue
        if score_min is not None and int(row.get("score") or 0) < score_min:
            continue
        if score_max is not None and int(row.get("score") or 0) > score_max:
            continue
        if only_fixable and int(row.get("fixable_issue_count") or 0) <= 0:
            continue
        filtered.append(row)
    return filtered


def filter_issue_rows(
    rows: list[dict[str, Any]],
    *,
    category: str | None,
    severity: str | None,
    issue_code: str | None,
    only_problems: bool,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        issues = row.get("issues") or []
        if only_problems and not issues:
            continue
        if category and not any(issue.get("category") == category for issue in issues):
            continue
        if severity and not any(issue.get("severity") == severity for issue in issues):
            continue
        if issue_code and not any(issue.get("code") == issue_code for issue in issues):
            continue
        filtered.append(row)
    return filtered


def sort_rows(rows: list[dict[str, Any]], sort_by: str) -> list[dict[str, Any]]:
    if sort_by == "score_asc":
        key = lambda row: (int(row.get("score") or 0), _clean(row.get("title")))
    elif sort_by == "critical":
        key = lambda row: (-int(row.get("critical_issue_count") or 0), int(row.get("score") or 0), _clean(row.get("title")))
    elif sort_by == "stock":
        key = lambda row: (-int(row.get("available_qty") or 0), int(row.get("score") or 0), _clean(row.get("title")))
    elif sort_by == "newest":
        key = lambda row: (-(row.get("created_at").timestamp() if row.get("created_at") else 0), _clean(row.get("title")))
    elif sort_by == "brand":
        key = lambda row: (_clean(row.get("brand_title")), _clean(row.get("series_title")), _clean(row.get("title")))
    elif sort_by == "series":
        key = lambda row: (_clean(row.get("series_title")), _clean(row.get("title")))
    elif sort_by == "title":
        key = lambda row: _clean(row.get("title"))
    else:
        key = lambda row: (-int(row.get("work_priority_score") or 0), int(row.get("score") or 0), _clean(row.get("title")))
    return sorted(rows, key=key)


def row_group(row: dict[str, Any], group_by: str) -> tuple[str, str]:
    if group_by == "brand":
        return f"brand:{row.get('brand_id') or 'missing'}", row.get("brand_title") or "Без бренда"
    if group_by == "series":
        return f"series:{row.get('series_id') or 'missing'}", row.get("series_title") or "Без серии"
    if group_by == "supplier":
        suppliers = row.get("suppliers") or []
        supplier_ids = {item.get("supplier_id") for item in suppliers if item.get("supplier_id")}
        if len(supplier_ids) > 1:
            return "supplier:multiple", "Несколько поставщиков"
        if suppliers:
            return f"supplier:{suppliers[0].get('supplier_id')}", suppliers[0].get("supplier_name") or "Поставщик"
        return "supplier:missing", "Без поставщика"
    if group_by == "equipment_type":
        return f"equipment:{row.get('equipment_type') or 'missing'}", row.get("equipment_type_label") or "Тип не определён"
    return "all", "Все товары"


def build_groups(rows: list[dict[str, Any]], group_by: str) -> list[dict[str, Any]]:
    if group_by == "none":
        return []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    labels: dict[str, str] = {}
    for row in rows:
        key, label = row_group(row, group_by)
        grouped[key].append(row)
        labels[key] = label
        row["group_key"] = key
        row["group_label"] = label
    result = []
    for key, items in grouped.items():
        result.append(
            {
                "key": key,
                "label": labels[key],
                "count": len(items),
                "average_score": round(sum(int(item.get("score") or 0) for item in items) / len(items)),
                "critical_products": sum(1 for item in items if int(item.get("critical_issue_count") or 0) > 0),
                "media_problem_products": sum(
                    1 for item in items if any(issue.get("category") == "media" for issue in item.get("issues") or [])
                ),
                "spec_problem_products": sum(
                    1 for item in items if any(issue.get("category") == "specs" for issue in item.get("issues") or [])
                ),
            }
        )
    return sorted(result, key=lambda item: (-item["critical_products"], item["average_score"], _clean(item["label"])))


def _options(values: Iterable[tuple[str, str, str | None]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str, str | None], int] = defaultdict(int)
    for value, label, parent in values:
        if value:
            counts[(value, label, parent)] += 1
    return [
        {"value": value, "label": label, "count": count, "parent_value": parent}
        for (value, label, parent), count in sorted(counts.items(), key=lambda item: _clean(item[0][1]))
    ]


def build_filter_options(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    supplier_values: list[tuple[str, str, str | None]] = []
    for row in rows:
        seen: set[int] = set()
        for supplier in row.get("suppliers") or []:
            supplier_id = supplier.get("supplier_id")
            if supplier_id and supplier_id not in seen:
                supplier_values.append((str(supplier_id), supplier.get("supplier_name") or f"Поставщик #{supplier_id}", None))
                seen.add(supplier_id)
    return {
        "equipment_types": _options(
            (row.get("equipment_type"), row.get("equipment_type_label") or row.get("equipment_type"), None)
            for row in rows
        ),
        "equipment_subtypes": _options(
            (
                row.get("equipment_subtype"),
                row.get("equipment_subtype_label") or row.get("equipment_subtype"),
                row.get("equipment_type"),
            )
            for row in rows
        ),
        "brands": _options(
            (str(row.get("brand_id") or ""), row.get("brand_title") or "", None)
            for row in rows
        ),
        "series": _options(
            (
                str(row.get("series_id") or ""),
                row.get("series_title") or "",
                str(row.get("brand_id") or "") or None,
            )
            for row in rows
        ),
        "suppliers": _options(supplier_values),
    }
