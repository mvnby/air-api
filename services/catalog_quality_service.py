from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models.media import MediaAsset
from models.product import Product, Tag
from models.supplier import ProductSupplierMapping, Supplier, SupplierOffer
from services.catalog_quality_filters import (
    build_builtin_view_counts,
    build_filter_options,
    build_groups,
    classify_product,
    enrich_work_priority,
    filter_dimension_rows,
    filter_issue_rows,
    sort_rows,
)
CATEGORY_LABELS = {
    "media": "Медиа",
    "identity": "Бренд и серия",
    "specs": "Характеристики",
    "commerce": "Цена и наличие",
    "supplier": "Поставщики",
}

SEVERITY_PENALTIES = {
    "critical": 30,
    "warning": 14,
    "info": 6,
}

ISSUE_LABELS = {
    "missing_brand": "Нет бренда",
    "missing_series": "Нет серии",
    "missing_main_image": "Нет главного фото",
    "single_image": "Только одно фото",
    "low_resolution_main_image": "Маленькое главное фото",
    "all_images_low_resolution": "Все фото маленькие",
    "external_media_not_ingested": "Фото вне медиатеки",
    "missing_price": "Нет цены",
    "missing_area": "Нет площади",
    "missing_cooling_power": "Нет мощности охлаждения",
    "missing_supplier_mapping": "Нет связи с поставщиком",
    "out_of_stock": "Нет доступного наличия",
}
@dataclass(frozen=True)
class ImageInfo:
    url: str
    width: int | None = None
    height: int | None = None
    source: str = "unknown"


@dataclass(frozen=True)
class QualityIssue:
    code: str
    category: str
    severity: str
    message: str
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "label": ISSUE_LABELS.get(self.code, self.code),
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "detail": self.detail,
        }


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).replace(",", ".").strip()))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _normalize_url(value: Any) -> str | None:
    if not value:
        return None
    url = str(value).strip()
    return url or None


def _image_urls_from_product(product: Product) -> list[str]:
    urls: list[str] = []

    def add(value: Any) -> None:
        url = _normalize_url(value)
        if url and url not in urls:
            urls.append(url)

    add(product.main_image)
    raw_images = product.images or []
    if isinstance(raw_images, dict):
        iterable_images = raw_images.values()
    elif isinstance(raw_images, list):
        iterable_images = raw_images
    else:
        iterable_images = [raw_images]
    for value in iterable_images:
        if isinstance(value, dict):
            add(value.get("url") or value.get("src"))
        else:
            add(value)
    for image in product.gallery_images or []:
        add(image.url)
    return urls


def _url_keys(url: str) -> set[str]:
    keys = {url}
    if url.startswith("/"):
        keys.add(url.lstrip("/"))
    else:
        keys.add(f"/{url}")

    parsed = urlparse(url)
    if parsed.path:
        keys.add(parsed.path)
        keys.add(parsed.path.lstrip("/"))
    return {key for key in keys if key}


def _is_local_media_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path if parsed.scheme else url
    return path.startswith("/media/") or path.startswith("media/")


def _local_media_path(base_dir: Path, url: str) -> Path | None:
    if not _is_local_media_url(url):
        return None
    parsed = urlparse(url)
    path = parsed.path if parsed.scheme else url
    clean_path = path.lstrip("/")
    if clean_path.startswith("media/"):
        return base_dir / clean_path
    return None


def _read_local_image_size(base_dir: Path, url: str) -> ImageInfo | None:
    path = _local_media_path(base_dir, url)
    if not path or not path.exists() or not path.is_file():
        return None
    try:
        with Image.open(path) as image:
            width, height = image.size
            return ImageInfo(url=url, width=width, height=height, source="file")
    except (OSError, UnidentifiedImageError):
        return None


def _spec_value(specs: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in specs and specs[key] not in (None, "", []):
            return specs[key]
    return None


class CatalogQualityService:
    @staticmethod
    async def build_report(
        session: AsyncSession,
        *,
        page: int = 1,
        limit: int = 40,
        q: str | None = None,
        category: str | None = None,
        severity: str | None = None,
        issue_code: str | None = None,
        only_problems: bool = True,
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
        sort_by: str = "priority",
        group_by: str = "none",
    ) -> dict[str, Any]:
        base_dir = Path.cwd()
        products = await CatalogQualityService._load_products(session=session, q=q)
        media_by_url = await CatalogQualityService._load_media_assets(session, products)
        supplier_context_by_product = await CatalogQualityService._load_supplier_context(session)
        local_size_cache: dict[str, ImageInfo | None] = {}

        rows = [
            CatalogQualityService._inspect_product(
                product=product,
                media_by_url=media_by_url,
                supplier_context_by_product=supplier_context_by_product,
                base_dir=base_dir,
                local_size_cache=local_size_cache,
            )
            for product in products
        ]

        filter_options = build_filter_options(rows)
        builtin_view_counts = build_builtin_view_counts(rows)
        scoped_rows = filter_dimension_rows(
            rows,
            equipment_type=equipment_type,
            equipment_subtype=equipment_subtype,
            brand_id=brand_id,
            series_id=series_id,
            series_state=series_state,
            supplier_id=supplier_id,
            supplier_state=supplier_state,
            publication=publication,
            availability=availability,
            priority=priority,
            score_min=score_min,
            score_max=score_max,
            only_fixable=only_fixable,
        )
        filtered = filter_issue_rows(
            scoped_rows,
            category=category,
            severity=severity,
            issue_code=issue_code,
            only_problems=only_problems,
        )
        summary = CatalogQualityService._build_summary(filtered)
        categories = CatalogQualityService._build_categories(filtered)
        filtered = sort_rows(filtered, sort_by)
        groups = build_groups(filtered, group_by)
        total_filtered = len(filtered)
        offset = (page - 1) * limit
        page_items = filtered[offset : offset + limit]
        score_values = [item["score"] for item in filtered]
        average_score = round(sum(score_values) / len(score_values)) if score_values else 100
        problem_products = sum(1 for item in filtered if item["issue_count"] > 0)
        critical_products = sum(
            1
            for item in filtered
            if any(issue["severity"] == "critical" for issue in item["issues"])
        )
        fixable_products = sum(1 for item in filtered if int(item.get("fixable_issue_count") or 0) > 0)
        severity_issue_counts = {severity_key: 0 for severity_key in ("critical", "warning", "info")}
        severity_product_counts = {severity_key: 0 for severity_key in ("critical", "warning", "info")}
        for item in filtered:
            present: set[str] = set()
            for issue in item["issues"]:
                severity_key = issue["severity"]
                severity_issue_counts[severity_key] += 1
                present.add(severity_key)
            for severity_key in present:
                severity_product_counts[severity_key] += 1

        return {
            "generated_at": datetime.now(),
            "total_products": total_filtered,
            "problem_products": problem_products,
            "critical_products": critical_products,
            "fixable_products": fixable_products,
            "average_score": average_score,
            "items": page_items,
            "summary": summary,
            "categories": categories,
            "groups": groups,
            "filter_options": filter_options,
            "builtin_view_counts": builtin_view_counts,
            "severity_issue_counts": severity_issue_counts,
            "severity_product_counts": severity_product_counts,
            "meta": {
                "total": total_filtered,
                "page": page,
                "limit": limit,
                "pages": max(1, (total_filtered + limit - 1) // limit),
            },
        }

    @staticmethod
    async def _load_products(session: AsyncSession, q: str | None = None) -> list[Product]:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.brand),
                selectinload(Product.series),
                selectinload(Product.gallery_images),
                selectinload(Product.tags).selectinload(Tag.group),
                selectinload(Product.supplier_mappings),
                selectinload(Product.local_stocks),
            )
            .order_by(Product.title)
        )
        query = (q or "").strip()
        if query:
            like = f"%{query}%"
            stmt = stmt.where(or_(Product.title.ilike(like), Product.slug.ilike(like)))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def _load_media_assets(
        session: AsyncSession,
        products: list[Product],
    ) -> dict[str, ImageInfo]:
        urls: set[str] = set()
        for product in products:
            for url in _image_urls_from_product(product):
                urls.update(_url_keys(url))
        if not urls:
            return {}

        stmt = select(MediaAsset).where(MediaAsset.url.in_(urls))
        result = await session.execute(stmt)
        media_by_url: dict[str, ImageInfo] = {}
        for asset in result.scalars().all():
            info = ImageInfo(
                url=asset.url,
                width=asset.width,
                height=asset.height,
                source="media_asset",
            )
            for key in _url_keys(asset.url):
                media_by_url[key] = info
        return media_by_url

    @staticmethod
    async def _load_supplier_context(session: AsyncSession) -> dict[int, list[dict[str, Any]]]:
        stmt = (
            select(ProductSupplierMapping, SupplierOffer, Supplier)
            .join(Supplier, Supplier.id == ProductSupplierMapping.supplier_id)
            .outerjoin(
                SupplierOffer,
                (SupplierOffer.supplier_id == ProductSupplierMapping.supplier_id)
                & (SupplierOffer.external_id == ProductSupplierMapping.external_id)
                & (SupplierOffer.is_active == True),  # noqa: E712
            )
            .where(ProductSupplierMapping.is_active == True)  # noqa: E712
        )
        result = await session.execute(stmt)
        contexts: dict[int, list[dict[str, Any]]] = {}
        for mapping, offer, supplier in result.all():
            contexts.setdefault(int(mapping.product_id), []).append(
                {
                    "supplier_id": int(supplier.id),
                    "supplier_name": supplier.name,
                    "qty": int(offer.qty or 0) if offer else 0,
                    "rrc_byn": float(offer.rrc_byn) if offer and offer.rrc_byn is not None else None,
                    "wholesale_value": float(offer.wholesale_value) if offer and offer.wholesale_value is not None else None,
                    "wholesale_currency": offer.wholesale_currency if offer else None,
                    "updated_at": offer.updated_at if offer else None,
                }
            )
        return contexts

    @staticmethod
    def _inspect_product(
        *,
        product: Product,
        media_by_url: dict[str, ImageInfo],
        supplier_context_by_product: dict[int, list[dict[str, Any]]],
        base_dir: Path,
        local_size_cache: dict[str, ImageInfo | None],
    ) -> dict[str, Any]:
        product_id = int(product.id or 0)
        specs = product.specs or {}
        image_infos = CatalogQualityService._resolve_product_images(
            product=product,
            media_by_url=media_by_url,
            base_dir=base_dir,
            local_size_cache=local_size_cache,
        )
        main_image_info = CatalogQualityService._resolve_image_info(
            product.main_image,
            media_by_url=media_by_url,
            base_dir=base_dir,
            local_size_cache=local_size_cache,
        )
        local_qty = sum(int(stock.qty or 0) for stock in product.local_stocks or [])
        supplier_context = supplier_context_by_product.get(product_id, [])
        offer_qty = sum(int(item.get("qty") or 0) for item in supplier_context)
        available_qty = local_qty + offer_qty
        active_mapping_count = len(supplier_context)
        issues = CatalogQualityService._collect_issues(
            product=product,
            specs=specs,
            image_infos=image_infos,
            main_image_info=main_image_info,
            available_qty=available_qty,
            active_mapping_count=active_mapping_count,
        )
        issue_dicts = [issue.as_dict() for issue in issues]
        score = CatalogQualityService._score(issues)
        media_status = CatalogQualityService._media_status(product, image_infos)
        equipment_type, equipment_type_label, equipment_subtype, equipment_subtype_label = classify_product(product)
        row = {
            "product_id": product_id,
            "title": product.title,
            "slug": product.slug,
            "brand_id": product.brand_id,
            "brand_title": product.brand.title if product.brand else None,
            "series_id": product.series_id,
            "series_title": product.series.title if product.series else None,
            "equipment_type": equipment_type,
            "equipment_type_label": equipment_type_label,
            "equipment_subtype": equipment_subtype,
            "equipment_subtype_label": equipment_subtype_label,
            "main_image": product.main_image,
            "price": int(product.price or 0),
            "is_published": bool(product.is_published),
            "score": score,
            "issue_count": len(issue_dicts),
            "image_count": len(image_infos),
            "main_image_width": main_image_info.width if main_image_info else None,
            "main_image_height": main_image_info.height if main_image_info else None,
            "media_status": media_status,
            "supplier_mapping_count": active_mapping_count,
            "suppliers": supplier_context,
            "available_qty": available_qty,
            "created_at": product.created_at,
            "critical_issue_count": sum(1 for issue in issue_dicts if issue["severity"] == "critical"),
            "issues": issue_dicts,
        }
        enrich_work_priority(row)
        return row

    @staticmethod
    def _resolve_product_images(
        *,
        product: Product,
        media_by_url: dict[str, ImageInfo],
        base_dir: Path,
        local_size_cache: dict[str, ImageInfo | None],
    ) -> list[ImageInfo]:
        image_infos: list[ImageInfo] = []
        for url in _image_urls_from_product(product):
            info = CatalogQualityService._resolve_image_info(
                url,
                media_by_url=media_by_url,
                base_dir=base_dir,
                local_size_cache=local_size_cache,
            )
            image_infos.append(info or ImageInfo(url=url))
        return image_infos

    @staticmethod
    def _resolve_image_info(
        url: str | None,
        *,
        media_by_url: dict[str, ImageInfo],
        base_dir: Path,
        local_size_cache: dict[str, ImageInfo | None],
    ) -> ImageInfo | None:
        normalized = _normalize_url(url)
        if not normalized:
            return None
        for key in _url_keys(normalized):
            if key in media_by_url:
                return media_by_url[key]
        cache_key = normalized
        if cache_key not in local_size_cache:
            local_size_cache[cache_key] = _read_local_image_size(base_dir, normalized)
        return local_size_cache[cache_key]

    @staticmethod
    def _collect_issues(
        *,
        product: Product,
        specs: dict[str, Any],
        image_infos: list[ImageInfo],
        main_image_info: ImageInfo | None,
        available_qty: int,
        active_mapping_count: int,
    ) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        if not product.brand_id:
            issues.append(
                QualityIssue(
                    code="missing_brand",
                    category="identity",
                    severity="critical",
                    message="Карточка не привязана к бренду.",
                )
            )
        if not product.series_id:
            issues.append(
                QualityIssue(
                    code="missing_series",
                    category="identity",
                    severity="warning",
                    message="Нет серии бренда, страница серии и группировка будут слабее.",
                )
            )
        if not _normalize_url(product.main_image):
            issues.append(
                QualityIssue(
                    code="missing_main_image",
                    category="media",
                    severity="critical",
                    message="Главное фото отсутствует.",
                )
            )
        if len(image_infos) == 1:
            issues.append(
                QualityIssue(
                    code="single_image",
                    category="media",
                    severity="warning",
                    message="У товара только одно изображение.",
                    detail="Для каталога и карточки лучше иметь главное фото и 2-4 дополнительных ракурса.",
                )
            )
        if main_image_info and CatalogQualityService._is_low_resolution(main_image_info):
            issues.append(
                QualityIssue(
                    code="low_resolution_main_image",
                    category="media",
                    severity="warning",
                    message="Главное фото слишком маленькое для нормальной карточки.",
                    detail=CatalogQualityService._image_size_label(main_image_info),
                )
            )
        known_sizes = [info for info in image_infos if info.width and info.height]
        if known_sizes and all(CatalogQualityService._is_low_resolution(info) for info in known_sizes):
            issues.append(
                QualityIssue(
                    code="all_images_low_resolution",
                    category="media",
                    severity="critical" if len(known_sizes) == len(image_infos) else "warning",
                    message="Все изображения с известным размером низкого разрешения.",
                )
            )
        unknown_external = [
            info.url
            for info in image_infos
            if not info.width and not info.height and not _is_local_media_url(info.url)
        ]
        if unknown_external:
            issues.append(
                QualityIssue(
                    code="external_media_not_ingested",
                    category="media",
                    severity="info",
                    message="Часть изображений хранится внешними ссылками и не видна медиатеке.",
                    detail=f"{len(unknown_external)} ссылок",
                )
            )
        if int(product.price or 0) <= 0:
            issues.append(
                QualityIssue(
                    code="missing_price",
                    category="commerce",
                    severity="critical",
                    message="Цена не заполнена или равна нулю.",
                )
            )
        if int(product.area or 0) <= 0 and not _as_int(_spec_value(specs, ("area_m2", "recommended_area_m2"))):
            issues.append(
                QualityIssue(
                    code="missing_area",
                    category="specs",
                    severity="warning",
                    message="Нет рекомендованной площади помещения.",
                )
            )
        if not product.power_cooling and not _as_float(
            _spec_value(specs, ("capacity_cooling_kw", "cooling_capacity_kw", "capacity_cooling"))
        ):
            issues.append(
                QualityIssue(
                    code="missing_cooling_power",
                    category="specs",
                    severity="warning",
                    message="Нет нормализованной мощности охлаждения.",
                )
            )
        if active_mapping_count <= 0:
            issues.append(
                QualityIssue(
                    code="missing_supplier_mapping",
                    category="supplier",
                    severity="warning",
                    message="Товар не связан с предложениями поставщиков.",
                )
            )
        if available_qty <= 0:
            issues.append(
                QualityIssue(
                    code="out_of_stock",
                    category="commerce",
                    severity="info",
                    message="Нет подтвержденного наличия у поставщика или на локальном складе.",
                )
            )
        return issues

    @staticmethod
    def _score(issues: list[QualityIssue]) -> int:
        penalty = sum(SEVERITY_PENALTIES.get(issue.severity, 0) for issue in issues)
        return max(0, min(100, 100 - penalty))

    @staticmethod
    def _is_low_resolution(info: ImageInfo) -> bool:
        if not info.width or not info.height:
            return False
        return info.width < 600 or info.height < 400

    @staticmethod
    def _image_size_label(info: ImageInfo) -> str:
        if not info.width or not info.height:
            return "размер неизвестен"
        return f"{info.width}x{info.height}px"

    @staticmethod
    def _media_status(product: Product, image_infos: list[ImageInfo]) -> str:
        if not _normalize_url(product.main_image):
            return "missing"
        if any(CatalogQualityService._is_low_resolution(info) for info in image_infos):
            return "low_resolution"
        if any(info.source == "unknown" for info in image_infos):
            return "unknown_dimensions"
        return "ok"

    @staticmethod
    def _build_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[str, dict[str, Any]] = {}
        for row in rows:
            seen_codes: set[str] = set()
            for issue in row["issues"]:
                code = issue["code"]
                if code in seen_codes:
                    continue
                seen_codes.add(code)
                if code not in counts:
                    counts[code] = {
                        "code": code,
                        "label": issue["label"],
                        "category": issue["category"],
                        "severity": issue["severity"],
                        "count": 0,
                    }
                counts[code]["count"] += 1
        severity_rank = {"critical": 0, "warning": 1, "info": 2}
        return sorted(
            counts.values(),
            key=lambda item: (severity_rank.get(item["severity"], 9), -item["count"], item["label"]),
        )

    @staticmethod
    def _build_categories(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        categories = {
            key: {
                "category": key,
                "label": label,
                "count": 0,
                "critical": 0,
                "warning": 0,
                "info": 0,
            }
            for key, label in CATEGORY_LABELS.items()
        }
        for row in rows:
            row_categories: set[str] = set()
            for issue in row["issues"]:
                category = issue["category"]
                severity = issue["severity"]
                if category not in categories:
                    categories[category] = {
                        "category": category,
                        "label": category,
                        "count": 0,
                        "critical": 0,
                        "warning": 0,
                        "info": 0,
                    }
                categories[category][severity] = int(categories[category].get(severity, 0)) + 1
                row_categories.add(category)
            for category in row_categories:
                categories[category]["count"] += 1
        return [item for item in categories.values() if item["count"] > 0]
