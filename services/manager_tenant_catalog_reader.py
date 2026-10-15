"""Bounded product content projection shared by system and partner Manager readers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from core.input_validation import validate_public_manual_url
from models import Brand, Product, ProductImage, ProductSeries, TenantOffer
from models.tenancy import TenantScope
from services.catalog_decision_projection import CatalogDecisionFilters, CatalogDecisionQueryService
from services.manager_tenant_catalog_service import ManagerTenantCatalogService
from services.product_image_processing_contract import ProductImageVariantType
from services.product_response_mapper import (
    _approved_ready_variant_url,
    _main_image_public_url,
    _public_image_url,
    _public_legacy_image_urls,
)
from services.product_serialization import parse_legacy_images, sanitize_specs
from services.spec_normalizer import normalize_specs
from services.spec_registry import INDOOR_TYPE_LABELS, SPEC_DEFINITIONS, QuantityKind
from services.yandex_business_feed_text import sanitize_yandex_description


_GROUP_LABELS = {
    "general": "Основные характеристики",
    "performance": "Производительность",
    "efficiency": "Энергоэффективность",
    "comfort": "Комфорт и условия работы",
    "installation": "Размеры и монтаж",
}
_SUMMARY_KEYS = (
    "area_m2", "capacity_cooling_kw", "capacity_heating_kw", "inverter",
    "wifi_state", "temp_range_heat", "noise_level_db",
)
_UNIT_LABELS = {
    "kW": "кВт", "W": "Вт", "m2": "м²", "m²": "м²", "m3/h": "м³/ч",
    "mm": "мм", "m": "м", "kg": "кг", "g": "г", "dB": "дБ", "A": "А",
    "C": "°C", "month": "мес.", "g/m": "г/м", "kWh/year": "кВт·ч/год", "l/h": "л/ч",
}


def _safe_media_url(value: str | None) -> str | None:
    try:
        return validate_public_manual_url(value or "")
    except ValueError:
        return None


def _group_for(key: str) -> str:
    spec = SPEC_DEFINITIONS[key]
    if key.startswith(("power_cons", "current_")) or key in {"eer", "cop", "seer", "scop", "energy_efficiency_class"}:
        return "efficiency"
    if key.startswith("capacity_") or spec.quantity_kind in {QuantityKind.AREA, QuantityKind.AIRFLOW}:
        return "performance"
    if spec.quantity_kind in {QuantityKind.NOISE, QuantityKind.TEMPERATURE}:
        return "comfort"
    if spec.quantity_kind in {QuantityKind.LENGTH, QuantityKind.WEIGHT, QuantityKind.REFRIGERANT_MASS}:
        return "installation"
    return "general"


def _value_text(value) -> str:
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if isinstance(value, (float, int)):
        return f"{value:g}"
    return str(value).strip()


def product_reader_specifications(product: Product) -> tuple[list[dict], list[dict]]:
    """Project every registered technical field, excluding arbitrary metadata keys."""
    normalized = normalize_specs(sanitize_specs(product.specs), keep_units=False)
    normalized.setdefault("inverter", bool(product.is_inverter))
    if product.power_cooling is not None:
        normalized.setdefault("capacity_cooling_kw", product.power_cooling)
    typed = normalized.get("__typed_specs", {})
    grouped: dict[str, list[dict]] = {key: [] for key in _GROUP_LABELS}
    by_key = {}
    for key, spec in SPEC_DEFINITIONS.items():
        raw = normalized.get(key)
        if raw is None or raw == "":
            continue
        payload = typed.get(key, {})
        unit = None
        if "values" in payload:
            separator = " … " if payload.get("type") == "range" else ", "
            value = separator.join(_value_text(item) for item in payload["values"])
            unit = payload.get("unit")
        elif "value" in payload:
            value = _value_text(payload["value"])
            unit = payload.get("unit")
        elif isinstance(raw, (str, int, float, bool)):
            value = _value_text(raw)
        elif isinstance(raw, list) and all(isinstance(item, (str, int, float, bool)) for item in raw):
            value = ", ".join(_value_text(item) for item in raw)
        else:
            continue
        if key == "wifi_state":
            value = {"builtin": "Встроенный", "ready": "Опция", "none": "Нет"}.get(value, value)
        elif key == "wifi_ready":
            value = {"true": "Да", "ready": "Опция", "false": "Нет"}.get(value, value)
        elif key == "indoor_type":
            value = INDOOR_TYPE_LABELS.get(value, value)
        if not value:
            continue
        item = {"key": key, "label": spec.label, "value": value, "unit": _UNIT_LABELS.get(unit, unit)}
        grouped[_group_for(key)].append(item)
        by_key[key] = item
    groups = [
        {"key": key, "label": label, "items": grouped[key]}
        for key, label in _GROUP_LABELS.items() if grouped[key]
    ]
    return groups, [by_key[key] for key in _SUMMARY_KEYS if key in by_key]


def _content_images(product: Product) -> tuple[str | None, list[dict]]:
    main_image = _safe_media_url(_main_image_public_url(product))
    candidates = [main_image]
    for image in sorted(product.gallery_images or [], key=lambda item: item.id or 0):
        candidates.append(
            _approved_ready_variant_url(image, ProductImageVariantType.FULL)
            or _public_image_url(image)
        )
    candidates.extend(_public_legacy_image_urls(product, parse_legacy_images(product.images)))
    images = []
    seen = set()
    for candidate in candidates:
        url = _safe_media_url(candidate)
        if url and url not in seen:
            images.append({"url": url, "alt": product.title})
            seen.add(url)
    return main_image, images


class ManagerTenantCatalogReader:
    @staticmethod
    async def get_product(
        session: AsyncSession, *, product_id: int, tenant_scope: TenantScope,
    ) -> dict | None:
        statement = (
            select(Product, Brand.title, ProductSeries.title, TenantOffer)
            .outerjoin(Brand, Brand.id == Product.brand_id)
            .outerjoin(ProductSeries, ProductSeries.id == Product.series_id)
            .outerjoin(TenantOffer, ManagerTenantCatalogService._offer_join(tenant_scope))
            .options(
                selectinload(Product.gallery_images).selectinload(ProductImage.variants),
                selectinload(Product.attachments),
            )
            .where(Product.id == product_id)
        )
        if not tenant_scope.is_system:
            statement = statement.where(Product.is_published.is_(True))
        row = (await session.execute(statement)).one_or_none()
        if row is None:
            return None
        product, brand_title, series_title, offer = row
        allowed = bool(product.is_published) if tenant_scope.is_system else bool(
            offer is not None and offer.status == "active" and offer.is_published
        )
        price = int(product.price) if tenant_scope.is_system else int(offer.price) if allowed else None
        selection_item = None
        if allowed:
            selection = await CatalogDecisionQueryService.list_products(
                session, tenant_scope=tenant_scope,
                filters=CatalogDecisionFilters(product_ids=(product_id,), is_published=True),
                page=1, limit=1, sort="title", direction="asc",
            )
            selection_item = next(iter(selection["items"]), None)
        groups, summary = product_reader_specifications(product)
        main_image, images = _content_images(product)
        manuals = []
        seen_manuals = set()
        for attachment in sorted(product.attachments or [], key=lambda item: item.id or 0):
            url = _safe_media_url(attachment.url)
            if attachment.kind == "manual" and url and url not in seen_manuals:
                manuals.append({"title": attachment.title or "Инструкция", "url": url})
                seen_manuals.add(url)
        return {
            "id": int(product.id), "title": product.title, "slug": product.slug or "",
            "brand_title": brand_title, "series_title": series_title,
            "main_image": main_image, "images": images,
            "description": sanitize_yandex_description(
                product.description, fallback="", limit=len(product.description or "") + 1,
            ),
            "summary_fields": summary, "specification_groups": groups, "manuals": manuals,
            "effective_price": price, "allowed": allowed, "selection_item": selection_item,
        }
