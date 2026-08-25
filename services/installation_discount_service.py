"""Authoritative product-margin policy for public installation discounts."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Mapping, Sequence

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from crud.installation_discount import InstallationDiscountDAO
from models import (
    GlobalConfig,
    InstallationDiscountPolicy,
    InstallationDiscountProductRule,
    Product,
)
from schemas_manager_installation_discounts import (
    ManagerInstallationDiscountPolicyResponse,
    ManagerInstallationDiscountPolicyUpdatePayload,
    ManagerInstallationDiscountProductResponse,
    ManagerInstallationDiscountRuleListResponse,
    ManagerInstallationDiscountRuleUpdatePayload,
    ManagerInstallationDiscountStatus,
)
from services.product_supply_metrics_service import ProductSupplyMetricsService

if TYPE_CHECKING:
    from services.public_catalog_visibility_service import PublicProductProjection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstallationDiscountDecision:
    product_id: int
    effective_price: int
    purchase_cost: float | None
    margin: float | None
    minimum_margin: int
    configured_discount: int
    applied_discount: int
    source: str
    status: ManagerInstallationDiscountStatus
    reason: str

    def snapshot(self) -> dict[str, object]:
        return {
            "policy_version": InstallationDiscountService.POLICY_VERSION,
            "source": self.source,
            "status": self.status.value,
            "reason": self.reason,
            "effective_product_price": self.effective_price,
            "purchase_cost": self.purchase_cost,
            "product_margin": self.margin,
            "minimum_margin": self.minimum_margin,
            "configured_discount": self.configured_discount,
            "applied_discount": self.applied_discount,
        }


class InstallationDiscountService:
    POLICY_VERSION = "installation-discount-v1"
    DEFAULT_DISCOUNT = 100
    DEFAULT_MINIMUM_MARGIN = 350
    MAX_DISCOUNT = 10_000

    @staticmethod
    def _purchase_cost(raw_cost: object, *, product_id: int) -> float | None:
        if raw_cost is None:
            return None
        try:
            cost = float(raw_cost)
        except (TypeError, ValueError):
            cost = math.nan
        if not math.isfinite(cost) or cost < 0:
            logger.warning(
                "INSTALLATION_DISCOUNT_COST_INVALID product_id=%s",
                product_id,
            )
            return None
        return round(cost, 2)

    @classmethod
    async def _legacy_discount(cls, session: AsyncSession) -> int:
        raw_discount = await InstallationDiscountDAO.get_legacy_default_discount(
            session
        )
        try:
            discount = int(str(raw_discount).strip())
        except (TypeError, ValueError):
            return 0
        return discount if 0 <= discount <= cls.MAX_DISCOUNT else 0

    @classmethod
    async def _policy(
        cls,
        session: AsyncSession,
    ) -> InstallationDiscountPolicy:
        policy = await InstallationDiscountDAO.get_policy(session)
        if policy is not None:
            return policy
        return InstallationDiscountPolicy(
            id=1,
            is_enabled=False,
            default_discount=await cls._legacy_discount(session),
            minimum_margin=cls.DEFAULT_MINIMUM_MARGIN,
        )

    @staticmethod
    def _policy_response(
        policy: InstallationDiscountPolicy,
    ) -> ManagerInstallationDiscountPolicyResponse:
        return ManagerInstallationDiscountPolicyResponse(
            is_enabled=bool(policy.is_enabled),
            default_discount=int(policy.default_discount),
            minimum_margin=int(policy.minimum_margin),
        )

    @classmethod
    async def resolve_for_products(
        cls,
        session: AsyncSession,
        *,
        products: Sequence[Product],
        effective_prices: Mapping[int, int],
        supply_metrics: Mapping[int, Mapping[str, object]] | None = None,
        include_economics: bool = False,
    ) -> dict[int, InstallationDiscountDecision]:
        product_by_id = {
            int(product.id): product
            for product in products
            if product.id is not None and int(product.id) in effective_prices
        }
        if not product_by_id:
            return {}

        policy = await cls._policy(session)
        rules = await InstallationDiscountDAO.get_rules_by_product_ids(
            session,
            set(product_by_id),
        )
        legacy_discount = (
            await cls._legacy_discount(session) if not policy.is_enabled else None
        )
        metrics: Mapping[int, Mapping[str, object]] = {}
        if policy.is_enabled or include_economics:
            metrics = supply_metrics or (
                await ProductSupplyMetricsService.compute_for_products(
                    session,
                    list(product_by_id.values()),
                )
            )

        decisions: dict[int, InstallationDiscountDecision] = {}
        for product_id in product_by_id:
            effective_price = int(effective_prices[product_id])
            rule = rules.get(product_id)
            configured_discount = int(
                rule.discount_amount if rule is not None else policy.default_discount
            )
            source = "product_override" if rule is not None else "default"
            raw_cost = (metrics.get(product_id) or {}).get("min_cost_byn")
            purchase_cost = cls._purchase_cost(raw_cost, product_id=product_id)
            margin = (
                round(effective_price - purchase_cost, 2)
                if purchase_cost is not None
                else None
            )

            if not policy.is_enabled:
                decisions[product_id] = InstallationDiscountDecision(
                    product_id=product_id,
                    effective_price=effective_price,
                    purchase_cost=purchase_cost,
                    margin=margin,
                    minimum_margin=int(policy.minimum_margin),
                    configured_discount=configured_discount,
                    applied_discount=int(legacy_discount or 0),
                    source="legacy_global",
                    status=ManagerInstallationDiscountStatus.legacy,
                    reason="margin_policy_disabled",
                )
                continue

            if configured_discount == 0:
                status_value = ManagerInstallationDiscountStatus.disabled
                reason = (
                    "product_override_disabled"
                    if rule is not None
                    else "default_disabled"
                )
                applied_discount = 0
            elif purchase_cost is None:
                status_value = ManagerInstallationDiscountStatus.blocked_missing_cost
                reason = "missing_purchase_cost"
                applied_discount = 0
            elif margin is None or margin < int(policy.minimum_margin):
                status_value = ManagerInstallationDiscountStatus.blocked_low_margin
                reason = "margin_below_threshold"
                applied_discount = 0
            else:
                status_value = ManagerInstallationDiscountStatus.active
                reason = "eligible"
                applied_discount = configured_discount

            decisions[product_id] = InstallationDiscountDecision(
                product_id=product_id,
                effective_price=effective_price,
                purchase_cost=purchase_cost,
                margin=margin,
                minimum_margin=int(policy.minimum_margin),
                configured_discount=configured_discount,
                applied_discount=applied_discount,
                source=source,
                status=status_value,
                reason=reason,
            )
        return decisions

    @classmethod
    async def decorate_public_projections(
        cls,
        session: AsyncSession,
        projections: Sequence[PublicProductProjection],
        *,
        supply_metrics: Mapping[int, Mapping[str, object]] | None = None,
    ) -> list[PublicProductProjection]:
        if not projections:
            return []
        products = [projection.product for projection in projections]
        effective_prices = {
            int(projection.product.id): int(projection.price)
            for projection in projections
            if projection.product.id is not None
        }
        decisions = await cls.resolve_for_products(
            session,
            products=products,
            effective_prices=effective_prices,
            supply_metrics=supply_metrics,
        )
        return [
            replace(
                projection,
                installation_discount=(
                    decisions[int(projection.product.id)].applied_discount
                    if projection.product.id is not None
                    and int(projection.product.id) in decisions
                    else 0
                ),
            )
            for projection in projections
        ]

    @staticmethod
    def _status_note(decision: InstallationDiscountDecision) -> str:
        notes = {
            ManagerInstallationDiscountStatus.legacy: (
                "Действует прежняя единая скидка: защита маржи пока выключена."
            ),
            ManagerInstallationDiscountStatus.active: (
                "Скидка применяется: маржа товара не ниже установленного минимума."
            ),
            ManagerInstallationDiscountStatus.disabled: (
                "Для товара скидка явно отключена."
            ),
            ManagerInstallationDiscountStatus.blocked_low_margin: (
                "Скидка не применяется: маржа товара ниже установленного минимума."
            ),
            ManagerInstallationDiscountStatus.blocked_missing_cost: (
                "Скидка не применяется: нет надёжной закупочной цены."
            ),
        }
        return notes[decision.status]

    @classmethod
    def _product_response(
        cls,
        product: Product,
        decision: InstallationDiscountDecision,
        *,
        has_override: bool,
    ) -> ManagerInstallationDiscountProductResponse:
        return ManagerInstallationDiscountProductResponse(
            product_id=int(product.id),
            title=product.title,
            slug=product.slug,
            main_image=product.main_image,
            retail_price=decision.effective_price,
            purchase_cost=decision.purchase_cost,
            margin=decision.margin,
            configured_discount=decision.configured_discount,
            applied_discount=decision.applied_discount,
            has_override=has_override,
            status=decision.status,
            status_note=cls._status_note(decision),
        )

    @classmethod
    async def list_rules(
        cls,
        session: AsyncSession,
        *,
        search: str | None,
        page: int,
        limit: int,
    ) -> ManagerInstallationDiscountRuleListResponse:
        policy = await cls._policy(session)
        rows, total = await InstallationDiscountDAO.list_rules(
            session,
            search=search,
            page=page,
            limit=limit,
        )
        products = [product for _, product in rows]
        decisions = await cls.resolve_for_products(
            session,
            products=products,
            effective_prices={
                int(product.id): int(product.price) for product in products
            },
            include_economics=True,
        )
        return ManagerInstallationDiscountRuleListResponse(
            policy=cls._policy_response(policy),
            items=[
                cls._product_response(
                    product,
                    decisions[int(product.id)],
                    has_override=True,
                )
                for _, product in rows
            ],
            page=page,
            limit=limit,
            total=total,
        )

    @classmethod
    async def search_products(
        cls,
        session: AsyncSession,
        *,
        search: str,
        limit: int,
    ) -> list[ManagerInstallationDiscountProductResponse]:
        products = await InstallationDiscountDAO.search_products(
            session,
            search=search,
            limit=limit,
        )
        decisions = await cls.resolve_for_products(
            session,
            products=products,
            effective_prices={
                int(product.id): int(product.price) for product in products
            },
            include_economics=True,
        )
        rules = await InstallationDiscountDAO.get_rules_by_product_ids(
            session,
            {int(product.id) for product in products},
        )
        return [
            cls._product_response(
                product,
                decisions[int(product.id)],
                has_override=int(product.id) in rules,
            )
            for product in products
        ]

    @classmethod
    async def update_policy(
        cls,
        session: AsyncSession,
        payload: ManagerInstallationDiscountPolicyUpdatePayload,
    ) -> ManagerInstallationDiscountPolicyResponse:
        policy = await InstallationDiscountDAO.get_policy(session)
        if policy is None:
            policy = InstallationDiscountPolicy(id=1)
        was_enabled = bool(policy.is_enabled)
        policy.is_enabled = payload.is_enabled
        policy.default_discount = payload.default_discount
        policy.minimum_margin = payload.minimum_margin
        policy.updated_at = datetime.now()
        InstallationDiscountDAO.add(session, policy)
        legacy_config = await InstallationDiscountDAO.get_legacy_discount_config(
            session
        )
        if payload.is_enabled:
            if legacy_config is None:
                legacy_config = GlobalConfig(
                    key="install_discount",
                    value="0",
                    description="Legacy storefront fallback; managed by installation discounts",
                )
            else:
                legacy_config.value = "0"
                legacy_config.updated_at = datetime.now()
            InstallationDiscountDAO.add(session, legacy_config)
        elif was_enabled and legacy_config is not None:
            legacy_config.value = str(payload.default_discount)
            legacy_config.updated_at = datetime.now()
            InstallationDiscountDAO.add(session, legacy_config)
        await session.commit()
        await session.refresh(policy)
        return cls._policy_response(policy)

    @classmethod
    async def upsert_rule(
        cls,
        session: AsyncSession,
        *,
        product_id: int,
        payload: ManagerInstallationDiscountRuleUpdatePayload,
    ) -> ManagerInstallationDiscountProductResponse:
        product = await InstallationDiscountDAO.get_product(session, product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )
        rule = await InstallationDiscountDAO.get_rule(session, product_id)
        if rule is None:
            rule = InstallationDiscountProductRule(
                product_id=product_id,
                discount_amount=payload.discount_amount,
            )
        else:
            rule.discount_amount = payload.discount_amount
            rule.updated_at = datetime.now()
        InstallationDiscountDAO.add(session, rule)
        await session.commit()
        decisions = await cls.resolve_for_products(
            session,
            products=[product],
            effective_prices={product_id: int(product.price)},
            include_economics=True,
        )
        return cls._product_response(
            product,
            decisions[product_id],
            has_override=True,
        )

    @staticmethod
    async def delete_rule(
        session: AsyncSession,
        *,
        product_id: int,
    ) -> None:
        rule = await InstallationDiscountDAO.get_rule(session, product_id)
        if rule is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Installation discount product rule not found",
            )
        await InstallationDiscountDAO.delete_rule(session, rule)
        await session.commit()


__all__ = ["InstallationDiscountDecision", "InstallationDiscountService"]
