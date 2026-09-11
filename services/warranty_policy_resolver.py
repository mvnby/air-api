"""Shared warranty policy selection for operational and public projections."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from crud.warranty_policy import WarrantyPolicyStore
from models import Product, WarrantyPolicy
from schemas import PublicProductWarrantyResponse


class WarrantyPolicyResolver:
    @staticmethod
    def _naive(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value

    @staticmethod
    def _matches(
        policy: WarrantyPolicy,
        *,
        product: Product | None,
        supplier_id: int | None,
        selected_series_ids: list[int],
    ) -> bool:
        if policy.supplier_id is not None and int(policy.supplier_id) != int(supplier_id or 0):
            return False
        if policy.product_id is not None and (
            not product or int(policy.product_id) != int(product.id or 0)
        ):
            return False
        if selected_series_ids and (
            not product or int(product.series_id or 0) not in selected_series_ids
        ):
            return False
        if policy.brand_id is not None and (
            not product or int(policy.brand_id) != int(product.brand_id or 0)
        ):
            return False
        return True

    @staticmethod
    def _score(policy: WarrantyPolicy) -> tuple[int, int]:
        if policy.product_id is not None:
            scope_specificity = 4
        elif policy.series_id is not None:
            scope_specificity = 3
        elif policy.brand_id is not None:
            scope_specificity = 2
        else:
            scope_specificity = 1
        return scope_specificity, int(policy.supplier_id is not None)

    @classmethod
    def _select(
        cls,
        policies: list[WarrantyPolicy],
        *,
        product: Product | None,
        supplier_id: int | None,
        series_ids_by_policy: dict[int, list[int]],
        moment: datetime,
    ) -> WarrantyPolicy | None:
        candidates = [
            policy
            for policy in policies
            if not (
                policy.effective_from
                and cls._naive(policy.effective_from) > moment
            )
            and not (
                policy.effective_until
                and cls._naive(policy.effective_until) < moment
            )
            and cls._matches(
                policy,
                product=product,
                supplier_id=supplier_id,
                selected_series_ids=series_ids_by_policy.get(
                    int(policy.id or 0), []
                ),
            )
        ]
        candidates.sort(
            key=lambda item: (cls._score(item), item.created_at, item.id or 0),
            reverse=True,
        )
        return candidates[0] if candidates else None

    @classmethod
    async def resolve_many(
        cls,
        session: AsyncSession,
        *,
        products: list[Product],
        supplier_id: int | None,
        coverage_type: str = "supplier",
        at: datetime | None = None,
        supplier_independent_only: bool = False,
    ) -> dict[int, WarrantyPolicy | None]:
        products_by_id = {
            int(product.id): product
            for product in products
            if product.id is not None
        }
        if not products_by_id:
            return {}

        policies = await WarrantyPolicyStore.load_active_policies(
            session,
            coverage_type=coverage_type,
            supplier_independent_only=supplier_independent_only,
        )
        series_ids_by_policy = await WarrantyPolicyStore._policy_series_ids(
            session, policies
        )
        moment = cls._naive(at) or datetime.now()
        return {
            product_id: cls._select(
                policies,
                product=product,
                supplier_id=supplier_id,
                series_ids_by_policy=series_ids_by_policy,
                moment=moment,
            )
            for product_id, product in products_by_id.items()
        }

    @classmethod
    async def resolve_one(
        cls,
        session: AsyncSession,
        *,
        product: Product | None,
        supplier_id: int | None,
        coverage_type: str = "supplier",
        at: datetime | None = None,
    ) -> WarrantyPolicy | None:
        policies = await WarrantyPolicyStore.load_active_policies(
            session,
            coverage_type=coverage_type,
        )
        series_ids_by_policy = await WarrantyPolicyStore._policy_series_ids(
            session, policies
        )
        return cls._select(
            policies,
            product=product,
            supplier_id=supplier_id,
            series_ids_by_policy=series_ids_by_policy,
            moment=cls._naive(at) or datetime.now(),
        )

    @classmethod
    async def resolve_public(
        cls,
        session: AsyncSession,
        products: list[Product],
        *,
        at: datetime | None = None,
    ) -> dict[int, PublicProductWarrantyResponse | None]:
        """Project only general rules for the already tenant-scoped products."""

        policies = await cls.resolve_many(
            session,
            products=products,
            supplier_id=None,
            coverage_type="supplier",
            at=at,
            supplier_independent_only=True,
        )
        return {
            product_id: (
                PublicProductWarrantyResponse(
                    duration_months=int(policy.duration_months),
                    maintenance_required=bool(policy.maintenance_required),
                    maintenance_interval_months=policy.maintenance_interval_months,
                    start_event=policy.start_event,
                    allowed_maintenance_provider=(
                        policy.allowed_maintenance_provider or "any"
                    ),
                    grace_period_days=int(policy.grace_period_days or 0),
                    terms=policy.terms,
                )
                if policy is not None and policy.duration_months is not None
                else None
            )
            for product_id, policy in policies.items()
        }
