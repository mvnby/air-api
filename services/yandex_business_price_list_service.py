from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Product, ServiceTariff, Tag
from services.tariffs_service import TariffsService


@dataclass(frozen=True)
class YandexCategory:
    id: int
    title: str


class YandexBusinessPriceListService:
    PRODUCT_FALLBACK_CATEGORY = YandexCategory(id=101, title="Товары")
    SERVICE_KIND_CATEGORIES = {
        "installation": YandexCategory(id=201, title="Монтаж"),
        "dismantling": YandexCategory(id=202, title="Демонтаж"),
        "maintenance": YandexCategory(id=203, title="Обслуживание"),
        "repair": YandexCategory(id=204, title="Ремонт"),
    }
    SERVICE_KIND_URLS = {
        "installation": "/montaj-konditionerov",
        "maintenance": "/obslujivanie-kondicionerov",
        "repair": "/services/repair",
        "dismantling": "/services",
    }

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        normalized = (base_url or "").strip().rstrip("/")
        if not normalized:
            return "https://mvn.by"
        if not re.match(r"^https?://", normalized, flags=re.IGNORECASE):
            normalized = f"https://{normalized}"
        return normalized

    @staticmethod
    def _absolute_url(base_url: str, value: str | None) -> str | None:
        raw = (value or "").strip()
        if not raw:
            return None
        if raw.startswith(("http://", "https://")):
            return raw
        return f"{base_url}/{raw.lstrip('/')}"

    @staticmethod
    def _shorten(value: str | None, limit: int) -> str:
        text = re.sub(r"\s+", " ", (value or "").strip())
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"

    @staticmethod
    def _append_text(parent: ET.Element, tag: str, value: str | int | float | None) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        child = ET.SubElement(parent, tag)
        child.text = text

    @staticmethod
    def _category_for_product(product: Product) -> YandexCategory:
        category_tags = [
            tag
            for tag in (product.tags or [])
            if tag.group and tag.group.slug == "category" and tag.title
        ]
        if not category_tags:
            return YandexBusinessPriceListService.PRODUCT_FALLBACK_CATEGORY
        tag = sorted(category_tags, key=lambda item: (item.sort_order, item.id or 0))[0]
        return YandexCategory(id=100000 + int(tag.id or 0), title=tag.title)

    @staticmethod
    def _product_vendor(product: Product) -> str:
        if product.brand and product.brand.title:
            return product.brand.title.strip()
        brand_tags = [
            tag.title.strip()
            for tag in (product.tags or [])
            if tag.group and tag.group.slug == "brand" and tag.title
        ]
        if brand_tags:
            return brand_tags[0]
        return (product.title or "Мастер Воздуха").split(" ", 1)[0]

    @staticmethod
    def _service_description(tariff: ServiceTariff) -> str:
        parts = [
            tariff.estimate_template,
            tariff.comment,
        ]
        if tariff.power_range:
            parts.append(f"Диапазон мощности: {tariff.power_range}.")
        if tariff.category:
            parts.append(f"Категория: {tariff.category}.")
        if tariff.service_kind == "installation" and float(tariff.included_route_meters or 0) > 0:
            meters = TariffsService._format_number(tariff.included_route_meters)
            parts.append(f"В базовую стоимость включено до {meters} м трассы.")
        return " ".join(part.strip() for part in parts if part and part.strip())

    @staticmethod
    async def _load_products(session: AsyncSession) -> list[Product]:
        stmt = (
            select(Product)
            .where(Product.is_published.is_(True))
            .where(Product.price > 0)
            .options(
                selectinload(Product.brand),
                selectinload(Product.tags).selectinload(Tag.group),
                selectinload(Product.gallery_images),
            )
            .order_by(Product.id)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def _load_tariffs(session: AsyncSession) -> list[ServiceTariff]:
        stmt = (
            select(ServiceTariff)
            .where(ServiceTariff.is_active.is_(True))
            .where(ServiceTariff.base_price > 0)
            .order_by(
                ServiceTariff.service_kind,
                ServiceTariff.sort_order,
                ServiceTariff.category,
                ServiceTariff.power_range,
                ServiceTariff.id,
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _append_categories(
        categories_node: ET.Element,
        product_categories: Iterable[YandexCategory],
        include_service_kinds: Iterable[str],
    ) -> None:
        fallback = YandexBusinessPriceListService.PRODUCT_FALLBACK_CATEGORY
        categories = {fallback.id: fallback}
        for category in product_categories:
            categories[category.id] = category
        for kind in include_service_kinds:
            category = YandexBusinessPriceListService.SERVICE_KIND_CATEGORIES.get(kind)
            if category:
                categories[category.id] = category

        for category in sorted(categories.values(), key=lambda item: item.id):
            node = ET.SubElement(categories_node, "category", id=str(category.id))
            node.text = category.title

    @staticmethod
    def _append_product_offer(
        offers_node: ET.Element,
        product: Product,
        category: YandexCategory,
        site_base_url: str,
    ) -> None:
        offer = ET.SubElement(offers_node, "offer", id=str(product.id))
        vendor = YandexBusinessPriceListService._product_vendor(product)
        description = YandexBusinessPriceListService._shorten(product.description or product.title, 3000)
        short_description = YandexBusinessPriceListService._shorten(product.description or product.title, 240)
        image = YandexBusinessPriceListService._absolute_url(site_base_url, product.main_image)
        url = (
            YandexBusinessPriceListService._absolute_url(site_base_url, f"/product/{product.slug}")
            if product.slug
            else None
        )

        YandexBusinessPriceListService._append_text(offer, "name", product.title)
        YandexBusinessPriceListService._append_text(offer, "vendor", vendor)
        YandexBusinessPriceListService._append_text(offer, "price", int(product.price or 0))
        YandexBusinessPriceListService._append_text(offer, "currencyId", "BYN")
        YandexBusinessPriceListService._append_text(offer, "categoryId", category.id)
        YandexBusinessPriceListService._append_text(offer, "picture", image)
        YandexBusinessPriceListService._append_text(offer, "description", description)
        YandexBusinessPriceListService._append_text(offer, "shortDescription", short_description)
        YandexBusinessPriceListService._append_text(offer, "url", url)

    @staticmethod
    def _append_service_offer(
        offers_node: ET.Element,
        tariff: ServiceTariff,
        site_base_url: str,
    ) -> None:
        category = YandexBusinessPriceListService.SERVICE_KIND_CATEGORIES.get(tariff.service_kind)
        if not category:
            return

        title = TariffsService.build_quick_add_title(tariff)
        description = YandexBusinessPriceListService._shorten(
            YandexBusinessPriceListService._service_description(tariff) or title,
            3000,
        )
        service_path = YandexBusinessPriceListService.SERVICE_KIND_URLS.get(tariff.service_kind, "/services")
        offer = ET.SubElement(offers_node, "offer", id=str(900000000 + int(tariff.id or 0)))

        YandexBusinessPriceListService._append_text(offer, "name", title)
        YandexBusinessPriceListService._append_text(offer, "vendor", "Мастер Воздуха")
        YandexBusinessPriceListService._append_text(offer, "price", int(tariff.base_price or 0))
        YandexBusinessPriceListService._append_text(offer, "currencyId", "BYN")
        YandexBusinessPriceListService._append_text(offer, "categoryId", category.id)
        YandexBusinessPriceListService._append_text(offer, "description", description)
        YandexBusinessPriceListService._append_text(
            offer,
            "shortDescription",
            YandexBusinessPriceListService._shorten(title, 240),
        )
        YandexBusinessPriceListService._append_text(
            offer,
            "url",
            YandexBusinessPriceListService._absolute_url(site_base_url, service_path),
        )

    @staticmethod
    async def build_xml(session: AsyncSession, *, site_base_url: str) -> bytes:
        base_url = YandexBusinessPriceListService._normalize_base_url(site_base_url)
        products = await YandexBusinessPriceListService._load_products(session)
        tariffs = await YandexBusinessPriceListService._load_tariffs(session)
        product_categories = [
            YandexBusinessPriceListService._category_for_product(product)
            for product in products
        ]
        service_kinds = {tariff.service_kind for tariff in tariffs}

        catalog = ET.Element("yml_catalog")
        shop = ET.SubElement(catalog, "shop")
        categories_node = ET.SubElement(shop, "categories")
        offers_node = ET.SubElement(shop, "offers")

        YandexBusinessPriceListService._append_categories(categories_node, product_categories, service_kinds)
        for product, category in zip(products, product_categories):
            YandexBusinessPriceListService._append_product_offer(offers_node, product, category, base_url)
        for tariff in tariffs:
            YandexBusinessPriceListService._append_service_offer(offers_node, tariff, base_url)

        ET.indent(catalog, space="    ")
        return ET.tostring(catalog, encoding="utf-8", xml_declaration=True)
