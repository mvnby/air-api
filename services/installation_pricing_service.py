"""Authoritative installation pricing for the public checkout."""

from __future__ import annotations

import logging
import math
from typing import Any, Sequence

from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import GlobalConfig, InstallationRate, Product, Service

logger = logging.getLogger(__name__)


class InstallationPricingError(ValueError):
    def __init__(self, message: str, *, code: str = "installation_pricing_invalid") -> None:
        super().__init__(message)
        self.code = code


class InstallationPricingService:
    PRICING_VERSION = "installation-v1"
    BUNDLE_DISCOUNT_CONFIG_KEY = "install_discount"
    MAX_BUNDLE_DISCOUNT = 10_000
    DEFAULT_METERS = 3.0
    PRODUCT_CATEGORY_SLUGS = ("wall", "cassette", "duct", "ceiling", "multisplit")

    @staticmethod
    def _normalize(value: Any) -> str:
        return str(value or "").strip().lower()

    @classmethod
    def _area_range_max(cls, power_range: str) -> int | None:
        key = cls._normalize(power_range)
        if "07-12" in key:
            return 35
        if "18-24" in key:
            return 70
        if "30-36" in key:
            return 100
        if any(value in key for value in ("area-20", "area-25", "area-35")):
            return 35
        if any(value in key for value in ("area-50", "area-70")):
            return 70
        if any(value in key for value in ("area-80", "area-100")):
            return 100
        return None

    @classmethod
    def _category_matches_rate(cls, rate_category: str, product_category: str) -> bool:
        rate = cls._normalize(rate_category)
        if product_category in {"wall", "duct", "multisplit"}:
            return rate == product_category
        if product_category in {"cassette", "ceiling"}:
            return rate in {"cassette", "ceiling", "cassette/ceiling"}
        return rate == product_category

    @classmethod
    def match_product_rate(
        cls,
        product: Product,
        rates: Sequence[InstallationRate],
    ) -> InstallationRate | None:
        tag_slugs = {
            cls._normalize(getattr(tag, "slug", ""))
            for tag in (getattr(product, "tags", None) or [])
        }
        product_category = next(
            (slug for slug in cls.PRODUCT_CATEGORY_SLUGS if slug in tag_slugs),
            "wall",
        )
        category_rates = [
            rate
            for rate in rates
            if cls._category_matches_rate(rate.category, product_category)
        ]
        if not category_rates:
            return None

        for rate in category_rates:
            power_range = cls._normalize(rate.power_range)
            if power_range == "all":
                return rate
            rate_slugs = {item.strip() for item in power_range.split(",") if item.strip()}
            if rate_slugs & tag_slugs:
                return rate

        product_area = int(getattr(product, "area", 0) or 0)
        if product_area > 0:
            area_rates = sorted(
                (
                    (rate, max_area)
                    for rate in category_rates
                    if (max_area := cls._area_range_max(rate.power_range)) is not None
                ),
                key=lambda item: item[1],
            )
            if area_rates:
                return next(
                    (rate for rate, max_area in area_rates if product_area <= max_area),
                    area_rates[-1][0],
                )
        return None

    @classmethod
    async def _bundle_discount(cls, session: AsyncSession) -> int:
        result = await session.execute(
            select(GlobalConfig).where(GlobalConfig.key == cls.BUNDLE_DISCOUNT_CONFIG_KEY)
        )
        config = result.scalar_one_or_none()
        if config is None:
            return 0
        try:
            discount = int(str(config.value).strip())
        except (TypeError, ValueError):
            logger.warning(
                "PUBLIC_INSTALLATION_CONFIG_INVALID key=%s",
                cls.BUNDLE_DISCOUNT_CONFIG_KEY,
            )
            return 0
        if not 0 <= discount <= cls.MAX_BUNDLE_DISCOUNT:
            logger.warning(
                "PUBLIC_INSTALLATION_CONFIG_OUT_OF_RANGE key=%s value=%s",
                cls.BUNDLE_DISCOUNT_CONFIG_KEY,
                discount,
            )
            return 0
        return discount

    @staticmethod
    def _option_snapshot(option: Service) -> dict[str, Any]:
        return {
            "service_id": int(option.id),
            "slug": option.slug,
            "title": option.title,
            "unit_price": int(option.base_price),
        }

    @classmethod
    def _snapshot_meta(
        cls,
        *,
        source: str | None,
        rate: InstallationRate | None,
        meters: float,
        status: str,
        reason: str | None,
        options: list[Service],
        base_price: int,
        extra_meters: float,
        extra_meters_price: int,
        bundle_discount: int,
        options_total: int,
        total: int,
    ) -> dict[str, Any]:
        normalized_meters: int | float = int(meters) if meters.is_integer() else meters
        return {
            "source": source or "public_checkout",
            "type": rate.category if rate else "General",
            "power_range": rate.power_range if rate else "",
            "meters": normalized_meters,
            "installation_rate_id": int(rate.id) if rate and rate.id is not None else None,
            "pricing_version": cls.PRICING_VERSION,
            "pricing_status": status,
            "requires_manager_quote": status != "fixed",
            "pricing_breakdown": {
                "currency": "BYN",
                "reason": reason,
                "base_price": base_price,
                "included_meters": int(rate.included_pipe_meters) if rate else None,
                "extra_meters": extra_meters,
                "extra_meter_unit_price": int(rate.extra_pipe_price) if rate else 0,
                "extra_meters_price": extra_meters_price,
                "bundle_discount": bundle_discount,
                "options": [cls._option_snapshot(option) for option in options],
                "options_total": options_total,
                "total": total,
            },
        }

    @classmethod
    def _log_quote_mismatch(
        cls,
        *,
        product_id: int | None,
        rate_id: int | None,
        client_hint: float,
        server_total: int,
    ) -> None:
        if math.isclose(client_hint, float(server_total), rel_tol=0, abs_tol=0.01):
            return
        logger.warning(
            "PUBLIC_INSTALLATION_PRICE_MISMATCH product_id=%s rate_id=%s client_hint=%s server_total=%s",
            product_id,
            rate_id,
            client_hint,
            server_total,
        )

    @classmethod
    async def price_public_items(
        cls,
        session: AsyncSession,
        items: Sequence[Any],
    ) -> list[dict[str, Any]]:
        has_installation = any(item.with_installation for item in items)
        product_ids = {int(item.product_id) for item in items if item.product_id is not None}
        products: dict[int, Product] = {}
        if product_ids:
            result = await session.execute(
                select(Product)
                .where(Product.id.in_(product_ids), Product.is_published.is_(True))
                .options(selectinload(Product.tags))
            )
            products = {int(product.id): product for product in result.scalars().all()}
            missing_product_ids = sorted(product_ids - products.keys())
            if missing_product_ids:
                raise InstallationPricingError(
                    f"Товар #{missing_product_ids[0]} недоступен для заказа",
                    code="product_not_available",
                )
            invalid_price_product = next(
                (product for product in products.values() if int(product.price) < 0),
                None,
            )
            if invalid_price_product is not None:
                raise InstallationPricingError(
                    f"Для товара #{invalid_price_product.id} требуется уточнение цены",
                    code="product_price_invalid",
                )

        rates: list[InstallationRate] = []
        if has_installation:
            rates_result = await session.execute(select(InstallationRate).order_by(InstallationRate.id))
            rates = list(rates_result.scalars().all())
        rates_by_id = {int(rate.id): rate for rate in rates if rate.id is not None}

        requested_option_slugs: list[str] = []
        for item in items:
            if not item.with_installation:
                continue
            option_slugs = list(item.installation_options or [])
            if len(option_slugs) != len(set(option_slugs)):
                raise InstallationPricingError(
                    "Опции монтажа не должны повторяться",
                    code="duplicate_installation_option",
                )
            requested_option_slugs.extend(option_slugs)

        options_by_slug: dict[str, Service] = {}
        if requested_option_slugs:
            options_result = await session.execute(
                select(Service).where(
                    Service.slug.in_(set(requested_option_slugs)),
                    Service.category == "installation_option",
                    Service.is_active.is_(True),
                )
            )
            options_by_slug = {
                option.slug: option
                for option in options_result.scalars().all()
            }
            unknown_options = sorted(set(requested_option_slugs) - options_by_slug.keys())
            if unknown_options:
                raise InstallationPricingError(
                    f"Неизвестная или недоступная опция монтажа: {unknown_options[0]}",
                    code="installation_option_not_available",
                )
            invalid_option = next(
                (option for option in options_by_slug.values() if int(option.base_price) < 0),
                None,
            )
            if invalid_option is not None:
                raise InstallationPricingError(
                    f"Для опции {invalid_option.slug} требуется уточнение цены",
                    code="installation_option_price_invalid",
                )

        has_product_installation = any(
            item.with_installation and item.product_id is not None
            for item in items
        )
        bundle_discount = await cls._bundle_discount(session) if has_product_installation else 0
        priced_items: list[dict[str, Any]] = []

        for item in items:
            product_id = int(item.product_id) if item.product_id is not None else None
            priced_item: dict[str, Any] = {
                "product_id": product_id,
                "quantity": int(item.quantity),
                "with_installation": bool(item.with_installation),
                "installation_rate_id": None,
                "installation_price": 0,
                "installation_meta": None,
                "installation_options": [],
            }
            if not item.with_installation:
                priced_items.append(priced_item)
                continue

            client_rate_id = int(item.installation_rate_id) if item.installation_rate_id else None
            if client_rate_id is not None and client_rate_id not in rates_by_id:
                raise InstallationPricingError(
                    f"Неизвестный тариф монтажа #{client_rate_id}",
                    code="installation_rate_not_available",
                )

            product = products.get(product_id) if product_id is not None else None
            if product is not None:
                rate = cls.match_product_rate(product, rates)
                if client_rate_id is not None and (
                    rate is None or int(rate.id) != client_rate_id
                ):
                    raise InstallationPricingError(
                        "Выбранный тариф монтажа не подходит для товара",
                        code="installation_rate_mismatch",
                    )
            else:
                rate = rates_by_id.get(client_rate_id) if client_rate_id is not None else None

            meta = item.installation_meta
            meters = float(meta.meters if meta is not None else cls.DEFAULT_METERS)
            source = meta.source if meta is not None else None
            options = [options_by_slug[slug] for slug in item.installation_options]
            option_total = sum(int(option.base_price) for option in options)
            rate_id = int(rate.id) if rate and rate.id is not None else None
            client_hint = float(item.installation_price or 0)

            if rate is None or not rate.is_fixed:
                reason = "no_matching_rate" if rate is None else "rate_requires_manual_quote"
                snapshot = cls._snapshot_meta(
                    source=source,
                    rate=rate,
                    meters=meters,
                    status="manual_quote",
                    reason=reason,
                    options=options,
                    base_price=0,
                    extra_meters=0,
                    extra_meters_price=0,
                    bundle_discount=0,
                    options_total=option_total,
                    total=0,
                )
                cls._log_quote_mismatch(
                    product_id=product_id,
                    rate_id=rate_id,
                    client_hint=client_hint,
                    server_total=0,
                )
                priced_item.update(
                    installation_rate_id=rate_id,
                    installation_meta=snapshot,
                )
                priced_items.append(priced_item)
                continue

            base_price = int(rate.base_price)
            extra_meter_price = int(rate.extra_pipe_price)
            included_meters = float(rate.included_pipe_meters)
            if base_price < 0 or extra_meter_price < 0 or included_meters < 0:
                raise InstallationPricingError(
                    f"Тариф монтажа #{rate_id} требует проверки",
                    code="installation_rate_price_invalid",
                )

            extra_meters = max(0.0, meters - included_meters)
            extra_meters_price = int(round(extra_meters * extra_meter_price))
            discount = min(bundle_discount, base_price + extra_meters_price) if product else 0
            server_total = base_price + extra_meters_price - discount + option_total
            snapshot = cls._snapshot_meta(
                source=source,
                rate=rate,
                meters=meters,
                status="fixed",
                reason=None,
                options=options,
                base_price=base_price,
                extra_meters=extra_meters,
                extra_meters_price=extra_meters_price,
                bundle_discount=discount,
                options_total=option_total,
                total=server_total,
            )
            cls._log_quote_mismatch(
                product_id=product_id,
                rate_id=rate_id,
                client_hint=client_hint,
                server_total=server_total,
            )
            priced_item.update(
                installation_rate_id=rate_id,
                installation_price=server_total,
                installation_meta=snapshot,
                installation_options=[option.slug for option in options],
            )
            priced_items.append(priced_item)

        return priced_items
