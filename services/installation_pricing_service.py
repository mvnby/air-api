"""Authoritative installation pricing for the public checkout."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import InstallationRate, Product, Service
from services.cooling_capacity import power_range_capacity_bounds
from services.installation_discount_service import (
    InstallationDiscountDecision,
    InstallationDiscountService,
)
from services.installation_product_profile import (
    InstallationProductProfile,
    build_installation_product_profile,
)
from services.order_product_link_command import OrderProductCatalogSnapshot

logger = logging.getLogger(__name__)


class InstallationPricingError(ValueError):
    def __init__(
        self, message: str, *, code: str = "installation_pricing_invalid"
    ) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class InstallationRateMatch:
    rate: InstallationRate | None
    profile: InstallationProductProfile
    reason: str | None


class InstallationPricingService:
    PRICING_VERSION = "installation-v1-discount-v1"
    DEFAULT_METERS = 3.0

    @staticmethod
    def _normalize(value: Any) -> str:
        return str(value or "").strip().lower()

    @classmethod
    def _normalized_rate_category(cls, value: str) -> str:
        normalized = cls._normalize(value).replace("_", "-")
        if normalized in {"floor-ceiling", "floor ceiling"}:
            return "ceiling"
        if normalized in {"cassette/ceiling", "cassette-ceiling"}:
            return "cassette/ceiling"
        return normalized

    @classmethod
    def _rate_power_tokens(cls, rate: InstallationRate) -> set[str]:
        return {
            token.strip()
            for token in cls._normalize(rate.power_range).split(",")
            if token.strip() and token.strip() != "all"
        }

    @classmethod
    def _select_rate(
        cls,
        rates: Sequence[InstallationRate],
        *,
        profile: InstallationProductProfile,
        match_capacity: bool,
    ) -> InstallationRate | None:
        for rate in rates:
            if cls._rate_power_tokens(rate) & profile.tag_slugs:
                return rate

        if profile.cooling_capacity_kw is not None:
            for rate in rates:
                bounds = power_range_capacity_bounds(rate.power_range)
                if bounds is None:
                    continue
                lower, upper = bounds
                if lower <= profile.cooling_capacity_kw <= upper:
                    return rate

        if match_capacity:
            return None

        return next(
            (rate for rate in rates if cls._normalize(rate.power_range) == "all"),
            None,
        )

    @classmethod
    def resolve_product_rate(
        cls,
        product: Product,
        rates: Sequence[InstallationRate],
    ) -> InstallationRateMatch:
        profile = build_installation_product_profile(product)
        if not profile.eligible or profile.equipment_category is None:
            return InstallationRateMatch(
                rate=None, profile=profile, reason=profile.reason
            )

        category_rates = [
            rate
            for rate in rates
            if cls._normalized_rate_category(rate.category)
            == profile.equipment_category
        ]
        rate = cls._select_rate(
            category_rates,
            profile=profile,
            match_capacity=profile.equipment_category == "wall",
        )

        if rate is None and profile.equipment_category in {"cassette", "ceiling"}:
            combined_manual_rates = [
                rate
                for rate in rates
                if cls._normalized_rate_category(rate.category) == "cassette/ceiling"
                and not rate.is_fixed
            ]
            rate = cls._select_rate(
                combined_manual_rates,
                profile=profile,
                match_capacity=False,
            )

        if rate is not None:
            reason = None if rate.is_fixed else "rate_requires_manual_quote"
            return InstallationRateMatch(rate=rate, profile=profile, reason=reason)
        if profile.equipment_category == "wall" and profile.cooling_capacity_kw is None:
            has_exact_power_tag = any(
                cls._rate_power_tokens(candidate) & profile.tag_slugs
                for candidate in category_rates
            )
            if not has_exact_power_tag:
                return InstallationRateMatch(
                    rate=None,
                    profile=profile,
                    reason="missing_cooling_capacity",
                )
        return InstallationRateMatch(
            rate=None, profile=profile, reason="no_matching_rate"
        )

    @classmethod
    def match_product_rate(
        cls,
        product: Product,
        rates: Sequence[InstallationRate],
    ) -> InstallationRate | None:
        return cls.resolve_product_rate(product, rates).rate

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
        discount_policy: dict[str, object] | None,
        options_total: int,
        total: int,
    ) -> dict[str, Any]:
        normalized_meters: int | float = int(meters) if meters.is_integer() else meters
        return {
            "source": source or "public_checkout",
            "type": rate.category if rate else "General",
            "power_range": rate.power_range if rate else "",
            "meters": normalized_meters,
            "installation_rate_id": int(rate.id)
            if rate and rate.id is not None
            else None,
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
                "discount_policy": discount_policy,
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
        catalog_snapshots: Mapping[int, OrderProductCatalogSnapshot] | None = None,
    ) -> list[dict[str, Any]]:
        has_installation = any(item.with_installation for item in items)
        product_ids = {
            int(item.product_id) for item in items if item.product_id is not None
        }
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
            rates_result = await session.execute(
                select(InstallationRate).order_by(InstallationRate.id)
            )
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
                option.slug: option for option in options_result.scalars().all()
            }
            unknown_options = sorted(
                set(requested_option_slugs) - options_by_slug.keys()
            )
            if unknown_options:
                raise InstallationPricingError(
                    f"Неизвестная или недоступная опция монтажа: {unknown_options[0]}",
                    code="installation_option_not_available",
                )
            invalid_option = next(
                (
                    option
                    for option in options_by_slug.values()
                    if int(option.base_price) < 0
                ),
                None,
            )
            if invalid_option is not None:
                raise InstallationPricingError(
                    f"Для опции {invalid_option.slug} требуется уточнение цены",
                    code="installation_option_price_invalid",
                )

        has_product_installation = any(
            item.with_installation and item.product_id is not None for item in items
        )
        discount_decisions: dict[int, InstallationDiscountDecision] = {}
        if has_product_installation:
            effective_prices = {
                product_id: (
                    int(catalog_snapshots[product_id].unit_price)
                    if catalog_snapshots is not None
                    else int(products[product_id].price)
                )
                for product_id in product_ids
            }
            discount_decisions = await InstallationDiscountService.resolve_for_products(
                session,
                products=list(products.values()),
                effective_prices=effective_prices,
            )
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

            client_rate_id = (
                int(item.installation_rate_id) if item.installation_rate_id else None
            )
            if client_rate_id is not None and client_rate_id not in rates_by_id:
                raise InstallationPricingError(
                    f"Неизвестный тариф монтажа #{client_rate_id}",
                    code="installation_rate_not_available",
                )

            product = products.get(product_id) if product_id is not None else None
            resolver_reason: str | None = None
            if product is not None:
                rate_match = cls.resolve_product_rate(product, rates)
                rate = rate_match.rate
                resolver_reason = rate_match.reason
                if client_rate_id is not None and (
                    rate is None or int(rate.id) != client_rate_id
                ):
                    raise InstallationPricingError(
                        "Выбранный тариф монтажа не подходит для товара",
                        code="installation_rate_mismatch",
                    )
            else:
                rate = (
                    rates_by_id.get(client_rate_id)
                    if client_rate_id is not None
                    else None
                )

            meta = item.installation_meta
            meters = float(meta.meters if meta is not None else cls.DEFAULT_METERS)
            source = meta.source if meta is not None else None
            options = [options_by_slug[slug] for slug in item.installation_options]
            option_total = sum(int(option.base_price) for option in options)
            rate_id = int(rate.id) if rate and rate.id is not None else None
            client_hint = float(item.installation_price or 0)

            if rate is None or not rate.is_fixed:
                reason = resolver_reason or (
                    "no_matching_rate" if rate is None else "rate_requires_manual_quote"
                )
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
                    discount_policy=None,
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
            discount_decision = (
                discount_decisions.get(product_id) if product_id is not None else None
            )
            discount = (
                min(
                    discount_decision.applied_discount,
                    base_price + extra_meters_price,
                )
                if discount_decision is not None
                else 0
            )
            discount_policy = (
                {
                    **discount_decision.snapshot(),
                    "applied_discount": discount,
                    "capped_by_installation_subtotal": (
                        discount < discount_decision.applied_discount
                    ),
                }
                if discount_decision is not None
                else None
            )
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
                discount_policy=discount_policy,
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
