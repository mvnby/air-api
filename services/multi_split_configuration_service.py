"""Shared, source-gated multi-split preview for the storefront and CRM."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api_contracts.multi_split import (
    ManagerMultiSplitPreviewResponse,
    MultiSplitComponent,
    MultiSplitOptionsResponse,
    MultiSplitPreviewRequest,
    MultiSplitPreviewResponse,
)
from models import MultiSplitCompatibilityProfile, Product, ProductTagLink, Tag
from models.tenancy import TenantScope
from services.catalog_form_factor import indoor_form_factor_expr
from services.product_collection_catalog_access import ProductCollectionCatalogAccess
from services.product_supply_metrics_service import ProductSupplyMetricsService


class MultiSplitSelectionError(ValueError):
    """A chosen component is missing, invisible, or not in its declared role."""


def assess_compatibility(
    profile: MultiSplitCompatibilityProfile | None,
    indoor_counts: Counter[int],
    room_count: int,
) -> tuple[str, str, bool]:
    """Trust only a reviewed profile with an exact model and quantity match."""
    try:
        source = urlsplit(profile.source_url or "") if profile else None
        source_ok = bool(source and source.scheme == "https" and source.hostname)
    except ValueError:
        source_ok = False
    verified = bool(
        profile
        and profile.verification_status == "verified"
        and source_ok
        and profile.source_version
        and profile.verified_at
        and profile.allowed_indoor_product_ids
        and profile.exact_combinations
    )
    if not verified or profile is None:
        return (
            "requires_specialist",
            "Точная совместимость и обязательные компоненты не подтверждены источником производителя. Требуется проверка специалистом.",
            False,
        )
    selected_signature = tuple(sorted(indoor_counts.items()))
    try:
        allowed_signatures = {
            tuple(sorted((int(line["indoor_product_id"]), int(line["quantity"])) for line in combo["lines"]))
            for combo in profile.exact_combinations
        }
        allowed_ids = {int(value) for value in profile.allowed_indoor_product_ids}
    except (KeyError, TypeError, ValueError):
        return (
            "requires_specialist",
            "Профиль совместимости заполнен неполно. Требуется проверка специалистом.",
            False,
        )
    count_ok = profile.max_indoor_units is None or room_count <= profile.max_indoor_units
    if not count_ok or not set(indoor_counts).issubset(allowed_ids) or selected_signature not in allowed_signatures:
        return (
            "incompatible",
            "Состав не входит в подтверждённые производителем сочетания для этого наружного блока.",
            True,
        )
    return (
        "confirmed",
        "Совместимость оборудования подтверждена для точного состава. Монтажные ограничения проверяются отдельно.",
        True,
    )


@dataclass(frozen=True)
class MultiSplitPreviewResult:
    public: MultiSplitPreviewResponse
    products: dict[int, Product]
    metrics: dict[int, dict[str, Any]]
    profile: MultiSplitCompatibilityProfile | None

    def manager_response(self, *, show_commercial: bool = True) -> ManagerMultiSplitPreviewResponse:
        if not show_commercial:
            return ManagerMultiSplitPreviewResponse(**self.public.model_dump())
        costs = [self.metrics[item.product_id].get("min_cost_byn") for item in self.public.components]
        cost = round(sum(float(value) * item.quantity for value, item in zip(costs, self.public.components)), 2) if all(value is not None for value in costs) else None
        return ManagerMultiSplitPreviewResponse(
            **self.public.model_dump(),
            purchase_cost_total_byn=cost,
            margin_byn=round(self.public.equipment_total_byn - cost, 2) if cost is not None else None,
        )


class MultiSplitConfigurationService:
    @staticmethod
    def _category_condition():
        return Product.id.in_(
            select(ProductTagLink.product_id)
            .join(Tag, Tag.id == ProductTagLink.tag_id)
            .where(Tag.slug == "cat-multi")
        )

    @classmethod
    async def list_options(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        kind: str,
        page: int,
        limit: int,
    ) -> MultiSplitOptionsResponse:
        visible_ids = await ProductCollectionCatalogAccess.visible_product_ids(
            session, tenant_scope=tenant_scope,
        )
        if not visible_ids:
            return MultiSplitOptionsResponse(items=[], meta={"page": page, "limit": limit, "total": 0, "pages": 1})
        conditions = (
            Product.id.in_(visible_ids),
            Product.is_published.is_(True),
            Product.product_kind == kind,
            cls._category_condition(),
        )
        total = int((await session.execute(select(func.count(Product.id)).where(*conditions))).scalar_one())
        rows = list((await session.execute(
            select(Product, indoor_form_factor_expr(session).label("indoor_form"))
            .where(*conditions)
            .order_by(Product.title.asc(), Product.id.asc())
            .offset((page - 1) * limit).limit(limit)
        )).all())
        products = [row[0] for row in rows]
        projections = await ProductCollectionCatalogAccess.visible_by_ids(
            session, tenant_scope=tenant_scope, product_ids=[int(product.id) for product in products],
        )
        metrics = await ProductSupplyMetricsService.compute_for_products(session, products)
        return MultiSplitOptionsResponse(
            items=[{
                "id": int(product.id), "title": product.title, "slug": product.slug,
                "product_kind": kind, "price_byn": int(projections[int(product.id)].price),
                "cooling_power_kw": product.power_cooling,
                "indoor_form_factor": row.indoor_form,
                "availability": metrics.get(int(product.id), {}).get("availability_status", "out_of_stock"),
            } for row in rows for product in [row[0]]],
            meta={"page": page, "limit": limit, "total": total, "pages": max(1, (total + limit - 1) // limit)},
        )

    @classmethod
    async def preview(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        request: MultiSplitPreviewRequest,
    ) -> MultiSplitPreviewResult:
        indoor_counts = Counter(room.indoor_product_id for room in request.rooms)
        selected_ids = {request.outdoor_product_id, *indoor_counts}
        projections = await ProductCollectionCatalogAccess.visible_by_ids(
            session, tenant_scope=tenant_scope, product_ids=selected_ids,
        )
        products = {
            product_id: projection.product
            for product_id, projection in projections.items()
            if projection.product.is_published
        }
        effective_prices = {product_id: int(projection.price) for product_id, projection in projections.items()}
        if set(products) != selected_ids:
            raise MultiSplitSelectionError("Один из блоков больше не доступен в каталоге.")
        if products[request.outdoor_product_id].product_kind != "outdoor_unit" or any(
            products[product_id].product_kind != "indoor_unit" for product_id in indoor_counts
        ):
            raise MultiSplitSelectionError("Выберите один наружный и отдельные внутренние блоки.")
        tagged_ids = set((await session.execute(
            select(Product.id).where(Product.id.in_(selected_ids), cls._category_condition())
        )).scalars().all())
        if tagged_ids != selected_ids:
            raise MultiSplitSelectionError("Товар не относится к компонентам мультисплита.")

        profile = (await session.execute(
            select(MultiSplitCompatibilityProfile).where(
                MultiSplitCompatibilityProfile.outdoor_product_id == request.outdoor_product_id,
            )
        )).scalar_one_or_none()
        status, explanation, verified = assess_compatibility(profile, indoor_counts, len(request.rooms))
        mandatory_ids = set(int(value) for value in profile.mandatory_component_product_ids or []) if verified and profile else set()
        if mandatory_ids & selected_ids:
            raise MultiSplitSelectionError("Подтверждённый профиль содержит повторный обязательный компонент.")
        if mandatory_ids:
            extra_projections = await ProductCollectionCatalogAccess.visible_by_ids(
                session, tenant_scope=tenant_scope, product_ids=mandatory_ids,
            )
            extra_products = {
                product_id: projection.product for product_id, projection in extra_projections.items()
                if projection.product.is_published
            }
            if set(extra_products) != mandatory_ids:
                raise MultiSplitSelectionError("Обязательный компонент отсутствует в каталоге; состав не заменён автоматически.")
            products.update(extra_products)
            effective_prices.update({product_id: int(projection.price) for product_id, projection in extra_projections.items()})

        quantities = Counter({request.outdoor_product_id: 1}) + indoor_counts + Counter({product_id: 1 for product_id in mandatory_ids})
        ordered_ids = [request.outdoor_product_id, *sorted(indoor_counts), *sorted(mandatory_ids)]
        metrics = await ProductSupplyMetricsService.compute_for_products(session, [products[product_id] for product_id in ordered_ids])
        components = [MultiSplitComponent(
            product_id=product_id,
            title=products[product_id].title,
            product_kind=products[product_id].product_kind,
            quantity=quantities[product_id],
            unit_price_byn=effective_prices[product_id],
            total_price_byn=effective_prices[product_id] * quantities[product_id],
            availability=metrics.get(product_id, {}).get("availability_status", "out_of_stock"),
        ) for product_id in ordered_ids]
        public = MultiSplitPreviewResponse(
            status=status,
            explanation=explanation,
            composition_complete=status == "confirmed",
            equipment_total_byn=sum(item.total_price_byn for item in components),
            components=components,
            source_url=profile.source_url if verified and profile else None,
            source_version=profile.source_version if verified and profile else None,
        )
        return MultiSplitPreviewResult(public=public, products=products, metrics=metrics, profile=profile if verified else None)
