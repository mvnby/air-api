"""Persistence and presentation helpers for warranty policy series scopes."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Brand, Product, ProductSeries, Supplier, WarrantyPolicy, WarrantyPolicySeriesLink


class WarrantyPolicyStore:
    @staticmethod
    async def load_active_policies(
        session: AsyncSession,
        *,
        coverage_type: str,
        supplier_independent_only: bool = False,
    ) -> list[WarrantyPolicy]:
        statement = select(WarrantyPolicy).where(
            WarrantyPolicy.is_active == True,
            WarrantyPolicy.coverage_type == coverage_type,
        )
        if supplier_independent_only:
            statement = statement.where(WarrantyPolicy.supplier_id.is_(None))
        return list((await session.execute(statement)).scalars().all())

    @staticmethod
    def policy_to_item(
        policy: WarrantyPolicy,
        *,
        scope_names: dict[str, dict[int, Any]] | None = None,
        series_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        names = scope_names or {}
        selected = list(series_ids or ([] if policy.series_id is None else [int(policy.series_id)]))
        return {
            "id": int(policy.id or 0), "name": policy.name, "coverage_type": policy.coverage_type,
            "supplier_id": policy.supplier_id, "brand_id": policy.brand_id, "series_id": policy.series_id,
            "series_ids": selected, "product_id": policy.product_id,
            "supplier_name": names.get("suppliers", {}).get(int(policy.supplier_id or 0)),
            "brand_title": names.get("brands", {}).get(int(policy.brand_id or 0)),
            "series_title": names.get("series", {}).get(int(policy.series_id or 0)),
            "series_titles": [names.get("series", {}).get(series_id, str(series_id)) for series_id in selected],
            "series_brand_id": names.get("series_brand_ids", {}).get(int(policy.series_id or 0)),
            "product_title": names.get("products", {}).get(int(policy.product_id or 0)),
            "duration_months": policy.duration_months, "start_event": policy.start_event,
            "maintenance_required": bool(policy.maintenance_required),
            "maintenance_interval_months": policy.maintenance_interval_months,
            "grace_period_days": int(policy.grace_period_days or 0),
            "allowed_maintenance_provider": policy.allowed_maintenance_provider, "terms": policy.terms,
            "effective_from": policy.effective_from, "effective_until": policy.effective_until,
            "is_active": bool(policy.is_active), "created_at": policy.created_at, "updated_at": policy.updated_at,
        }

    @staticmethod
    async def _policy_series_ids(
        session: AsyncSession, policies: list[WarrantyPolicy]
    ) -> dict[int, list[int]]:
        policy_ids = [int(policy.id) for policy in policies if policy.id is not None]
        selected: dict[int, list[int]] = {policy_id: [] for policy_id in policy_ids}
        if policy_ids:
            result = await session.execute(
                select(WarrantyPolicySeriesLink.policy_id, WarrantyPolicySeriesLink.series_id)
                .where(WarrantyPolicySeriesLink.policy_id.in_(policy_ids))
                .order_by(WarrantyPolicySeriesLink.policy_id, WarrantyPolicySeriesLink.sort_order, WarrantyPolicySeriesLink.id)
            )
            for policy_id, series_id in result.all():
                selected[int(policy_id)].append(int(series_id))
        for policy in policies:
            if policy.id is not None and not selected[int(policy.id)] and policy.series_id is not None:
                selected[int(policy.id)] = [int(policy.series_id)]
        return selected

    @staticmethod
    async def _policy_scope_names(
        session: AsyncSession,
        policies: list[WarrantyPolicy],
        series_ids_by_policy: dict[int, list[int]],
    ) -> dict[str, dict[int, Any]]:
        lookups: tuple[tuple[str, Any, Any, set[int]], ...] = (
            ("suppliers", Supplier, Supplier.name, {int(item.supplier_id) for item in policies if item.supplier_id}),
            ("brands", Brand, Brand.title, {int(item.brand_id) for item in policies if item.brand_id}),
            ("products", Product, Product.title, {int(item.product_id) for item in policies if item.product_id}),
        )
        names: dict[str, dict[int, Any]] = {}
        for key, model, title_field, ids in lookups:
            if not ids:
                names[key] = {}
                continue
            result = await session.execute(select(model.id, title_field).where(model.id.in_(ids)))
            names[key] = {int(item_id): str(title) for item_id, title in result.all()}
        series_ids = {
            series_id for policy in policies for series_id in series_ids_by_policy.get(int(policy.id or 0), [])
        }
        names["series"] = {}
        names["series_brand_ids"] = {}
        if series_ids:
            result = await session.execute(
                select(ProductSeries.id, ProductSeries.title, ProductSeries.brand_id).where(ProductSeries.id.in_(series_ids))
            )
            for series_id, title, brand_id in result.all():
                names["series"][int(series_id)] = str(title)
                if brand_id is not None:
                    names["series_brand_ids"][int(series_id)] = int(brand_id)
        return names

    @staticmethod
    def _normalized_series_ids(value: Any) -> list[int]:
        result: list[int] = []
        for raw_id in value or []:
            series_id = int(raw_id)
            if series_id not in result:
                result.append(series_id)
        return result

    @staticmethod
    async def _replace_policy_series(
        session: AsyncSession, *, policy_id: int, series_ids: list[int]
    ) -> None:
        await session.execute(delete(WarrantyPolicySeriesLink).where(WarrantyPolicySeriesLink.policy_id == policy_id))
        session.add_all(
            [
                WarrantyPolicySeriesLink(policy_id=policy_id, series_id=series_id, sort_order=index)
                for index, series_id in enumerate(series_ids)
            ]
        )
        await session.flush()
