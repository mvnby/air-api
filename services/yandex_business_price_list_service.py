from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from core.config import settings
from crud.product_collection import ProductCollectionDAO
from models import Product, ProductImage, ServiceTariff
from services.product_collection_resolver import ProductCollectionResolver, utc_now
from services.product_image_processing_contract import (
    ProductImageManualQualityStatus,
    ProductImageProcessingStatus,
    ProductImageVariantType,
)
from services.tariffs_service import TariffsService
from services.yandex_business_feed_text import sanitize_yandex_description


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class YandexCategory:
    id: int
    title: str


@dataclass(frozen=True)
class ProductOffer:
    product: Product
    category: YandexCategory


class YandexBusinessPriceListService:
    CATEGORY_RANGE_SIZE = 1_000_000
    COLLECTION_CATEGORY_OFFSET = 1_000_000
    BRAND_CATEGORY_OFFSET = 2_000_000
    UNBRANDED_CATEGORY = YandexCategory(id=3_000_000, title="Другие модели")
    SURFACE_KEY = "yandex_business"
    SLOT_KEY = "categories"

    SERVICE_KIND_CATEGORIES = {
        "installation": YandexCategory(id=201, title="Монтаж"),
        "dismantling": YandexCategory(id=202, title="Демонтаж"),
        "maintenance": YandexCategory(id=203, title="Обслуживание"),
        "repair": YandexCategory(id=204, title="Ремонт"),
        "pre_install": YandexCategory(id=205, title="Закладка коммуникаций"),
    }
    SERVICE_KIND_URLS = {
        "installation": "/montaj-konditionerov",
        "pre_install": "/services/zakladka-kommunikaciy-kondicionera",
        "maintenance": "/obslujivanie-kondicionerov",
        "repair": "/services/repair",
        "dismantling": "/services",
    }
    _IMAGE_VARIANT_ORDER = {
        ProductImageVariantType.CARD.value: 0,
        ProductImageVariantType.FULL.value: 1,
        ProductImageVariantType.PROCESSED.value: 2,
        ProductImageVariantType.ORIGINAL.value: 3,
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
    def _is_yandex_image_url(value: str | None) -> bool:
        path = urlsplit((value or "").strip()).path.lower()
        return path.endswith((".jpg", ".jpeg", ".png"))

    @staticmethod
    def _same_image_url(left: str | None, right: str | None) -> bool:
        if not left or not right:
            return False
        return left == right or left.strip("/") == right.strip("/")

    @classmethod
    def _product_picture(cls, product: Product, base_url: str) -> str | None:
        source = next(
            (
                image
                for image in (product.gallery_images or [])
                if cls._same_image_url(image.url, product.main_image)
            ),
            None,
        )
        if source is not None:
            variants = sorted(
                source.variants or [],
                key=lambda item: (
                    cls._IMAGE_VARIANT_ORDER.get(item.variant_type, 99),
                    int(item.id or 0),
                ),
            )
            for variant in variants:
                is_public_variant = (
                    variant.variant_type == ProductImageVariantType.ORIGINAL.value
                    or variant.manual_quality_status
                    == ProductImageManualQualityStatus.APPROVED.value
                )
                if (
                    variant.processing_status == ProductImageProcessingStatus.READY.value
                    and is_public_variant
                    and cls._is_yandex_image_url(variant.url)
                ):
                    return cls._absolute_url(base_url, variant.url)
        if cls._is_yandex_image_url(product.main_image):
            return cls._absolute_url(base_url, product.main_image)
        return None

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
    def _product_vendor(product: Product) -> str:
        if product.brand and product.brand.title:
            return product.brand.title.strip()
        return (product.title or "Мастер Воздуха").split(" ", 1)[0]

    @staticmethod
    def _service_description(tariff: ServiceTariff) -> str:
        parts = [tariff.effective_full_description, tariff.comment]
        if tariff.power_range:
            parts.append(f"Диапазон мощности: {tariff.power_range}.")
        if tariff.category:
            parts.append(f"Категория: {tariff.category}.")
        if (
            TariffsService.supports_route_meters(tariff.service_kind)
            and float(tariff.included_route_meters or 0) > 0
        ):
            meters = TariffsService._format_number(tariff.included_route_meters)
            parts.append(
                f"В базовую стоимость включено до {meters} м трассы."
            )
        return " ".join(part.strip() for part in parts if part and part.strip())

    @staticmethod
    async def _load_products(session: AsyncSession) -> list[Product]:
        stmt = (
            select(Product)
            .where(Product.is_published.is_(True), Product.price > 0)
            .options(
                selectinload(Product.brand),
                selectinload(Product.gallery_images).selectinload(ProductImage.variants),
            )
            .order_by(Product.id.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().unique().all())

    @staticmethod
    async def _load_tariffs(session: AsyncSession) -> list[ServiceTariff]:
        stmt = (
            select(ServiceTariff)
            .where(ServiceTariff.is_active.is_(True), ServiceTariff.base_price > 0)
            .order_by(
                ServiceTariff.sort_order.asc(),
                ServiceTariff.category.asc(),
                ServiceTariff.power_range.asc(),
                ServiceTariff.id.asc(),
            )
        )
        result = await session.execute(stmt)
        tariffs = list(result.scalars().all())
        service_rank = {
            kind: index
            for index, kind in enumerate(
                YandexBusinessPriceListService.SERVICE_KIND_CATEGORIES
            )
        }
        return sorted(
            tariffs,
            key=lambda item: (
                service_rank.get(item.service_kind, 999),
                item.sort_order,
                item.category,
                item.power_range,
                int(item.id or 0),
            ),
        )

    @classmethod
    def _scoped_category_id(cls, offset: int, entity_id: int | None) -> int:
        value = int(entity_id or 0)
        if value <= 0 or value >= cls.CATEGORY_RANGE_SIZE:
            raise ValueError(f"Yandex Business category source ID is out of range: {value}")
        return offset + value

    @classmethod
    async def _build_product_catalog(
        cls,
        session: AsyncSession,
        products: list[Product],
    ) -> tuple[list[YandexCategory], list[ProductOffer]]:
        products_by_id = {int(product.id): product for product in products}
        claimed_ids: set[int] = set()
        categories: list[YandexCategory] = []
        offers: list[ProductOffer] = []

        placements = await ProductCollectionDAO.list_placements(
            session,
            surface_key=cls.SURFACE_KEY,
            slot_key=cls.SLOT_KEY,
            now=utc_now(),
        )
        for _placement, collection in placements:
            resolved = await ProductCollectionResolver.resolve(
                session,
                collection=collection,
                surface_key=cls.SURFACE_KEY,
                slot_key=cls.SLOT_KEY,
                enforce_publication=True,
            )
            if resolved["below_min_items"]:
                continue
            selected = []
            for item in resolved["items"]:
                product_id = int(item["product"].id)
                product = products_by_id.get(product_id)
                if product is None or product_id in claimed_ids:
                    continue
                selected.append(product)
                claimed_ids.add(product_id)
            if not selected:
                continue
            category = YandexCategory(
                id=cls._scoped_category_id(
                    cls.COLLECTION_CATEGORY_OFFSET,
                    collection.id,
                ),
                title=collection.public_title,
            )
            categories.append(category)
            offers.extend(ProductOffer(product=product, category=category) for product in selected)

        remaining = [
            product for product in products if int(product.id) not in claimed_ids
        ]
        branded: dict[int, list[Product]] = {}
        brands = {}
        unbranded: list[Product] = []
        for product in remaining:
            if product.brand and product.brand.id is not None:
                brand_id = int(product.brand.id)
                brands[brand_id] = product.brand
                branded.setdefault(brand_id, []).append(product)
            else:
                unbranded.append(product)

        sorted_brands = sorted(
            brands.values(),
            key=lambda brand: (
                int(brand.sort_order or 0),
                (brand.title or "").casefold(),
                int(brand.id or 0),
            ),
        )
        for brand in sorted_brands:
            brand_products = sorted(
                branded[int(brand.id)],
                key=lambda product: (
                    (product.title or "").casefold(),
                    int(product.id or 0),
                ),
            )
            category = YandexCategory(
                id=cls._scoped_category_id(cls.BRAND_CATEGORY_OFFSET, brand.id),
                title=brand.title,
            )
            categories.append(category)
            offers.extend(
                ProductOffer(product=product, category=category)
                for product in brand_products
            )

        if unbranded:
            categories.append(cls.UNBRANDED_CATEGORY)
            offers.extend(
                ProductOffer(product=product, category=cls.UNBRANDED_CATEGORY)
                for product in sorted(
                    unbranded,
                    key=lambda product: (
                        (product.title or "").casefold(),
                        int(product.id or 0),
                    ),
                )
            )
        return categories, offers

    @classmethod
    def _append_product_offer(
        cls,
        offers_node: ET.Element,
        offer_data: ProductOffer,
        site_base_url: str,
    ) -> None:
        product = offer_data.product
        offer = ET.SubElement(offers_node, "offer", id=str(product.id))
        description = sanitize_yandex_description(
            product.description,
            fallback=product.title,
            limit=3000,
        )
        short_description = sanitize_yandex_description(
            product.description,
            fallback=product.title,
            limit=240,
        )
        cls._append_text(offer, "name", product.title)
        cls._append_text(offer, "vendor", cls._product_vendor(product))
        cls._append_text(offer, "price", int(product.price or 0))
        cls._append_text(offer, "currencyId", "BYN")
        cls._append_text(offer, "categoryId", offer_data.category.id)
        cls._append_text(offer, "picture", cls._product_picture(product, site_base_url))
        cls._append_text(offer, "description", description)
        cls._append_text(offer, "shortDescription", short_description)
        cls._append_text(
            offer,
            "url",
            cls._absolute_url(site_base_url, f"/product/{product.slug}"),
        )

    @classmethod
    def _append_service_offer(
        cls,
        offers_node: ET.Element,
        tariff: ServiceTariff,
        site_base_url: str,
    ) -> None:
        category = cls.SERVICE_KIND_CATEGORIES.get(tariff.service_kind)
        if not category:
            return
        title = TariffsService.build_quick_add_title(tariff)
        description = sanitize_yandex_description(
            cls._service_description(tariff),
            fallback=title,
            limit=3000,
        )
        service_path = cls.SERVICE_KIND_URLS.get(tariff.service_kind, "/services")
        offer = ET.SubElement(offers_node, "offer", id=str(900000000 + int(tariff.id or 0)))
        cls._append_text(offer, "name", title)
        cls._append_text(offer, "vendor", "Мастер Воздуха")
        cls._append_text(offer, "price", int(tariff.base_price or 0))
        cls._append_text(offer, "currencyId", "BYN")
        cls._append_text(offer, "categoryId", category.id)
        cls._append_text(offer, "description", description)
        cls._append_text(
            offer,
            "shortDescription",
            sanitize_yandex_description(title, fallback=title, limit=240),
        )
        cls._append_text(
            offer,
            "url",
            cls._absolute_url(site_base_url, service_path),
        )

    @classmethod
    async def build_xml(cls, session: AsyncSession) -> bytes:
        base_url = cls._normalize_base_url(settings.PUBLIC_SITE_URL)
        products = await cls._load_products(session)
        tariffs = await cls._load_tariffs(session)
        product_categories, product_offers = await cls._build_product_catalog(
            session,
            products,
        )
        omitted_picture_count = sum(
            1
            for offer_data in product_offers
            if cls._product_picture(offer_data.product, base_url) is None
        )
        if omitted_picture_count:
            logger.info(
                "Yandex Business feed omitted incompatible or missing pictures",
                extra={
                    "omitted_picture_count": omitted_picture_count,
                    "product_offer_count": len(product_offers),
                },
            )
        service_kinds = {tariff.service_kind for tariff in tariffs}

        catalog = ET.Element("yml_catalog")
        shop = ET.SubElement(catalog, "shop")
        categories_node = ET.SubElement(shop, "categories")
        offers_node = ET.SubElement(shop, "offers")

        categories = list(product_categories)
        categories.extend(
            category
            for kind, category in cls.SERVICE_KIND_CATEGORIES.items()
            if kind in service_kinds
        )
        category_ids = [category.id for category in categories]
        if len(category_ids) != len(set(category_ids)):
            raise ValueError("Yandex Business category ID collision")
        for category in categories:
            node = ET.SubElement(categories_node, "category", id=str(category.id))
            node.text = category.title

        for offer_data in product_offers:
            cls._append_product_offer(offers_node, offer_data, base_url)
        for tariff in tariffs:
            cls._append_service_offer(offers_node, tariff, base_url)

        ET.indent(catalog, space="    ")
        return ET.tostring(catalog, encoding="utf-8", xml_declaration=True)
