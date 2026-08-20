"""Server-side catalog decision query and explicit visibility boundary.

This first slice intentionally exposes only the canonical MVN system scope.
``CatalogDecisionProjection`` is the seam for later independent and sponsored
tenant policies: each must supply an eligible offer relation before aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import Float, and_, case, cast, exists, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.product import ProductDAO
from models import Brand, Product, ProductSeries, ProductTagLink, Tag
from models.supplier import ProductLocalStock, ProductSupplierMapping, Supplier, SupplierOffer
from models.tenancy import TenantScope
from services.fx_rate_service import FxRateService


class CatalogDecisionScopeError(PermissionError):
    """Raised when a non-system scope reaches the system supplier projection."""


@dataclass(frozen=True)
class CatalogDecisionFilters:
    search: str | None = None
    cooling_min_kw: float | None = None
    cooling_max_kw: float | None = None
    area_min: float | None = None
    area_max: float | None = None
    category: Literal["household", "multi", "semi_industrial"] | None = None
    indoor_form_factor: Literal["wall", "cassette", "duct", "floor_ceiling", "column"] | None = None
    brand_ids: tuple[int, ...] = ()
    series_ids: tuple[int, ...] = ()
    is_inverter: bool | None = None
    wifi: Literal["builtin", "ready", "none"] | None = None
    availability: Literal["in_stock", "out_of_stock"] | None = None
    is_published: bool | None = None


class CatalogDecisionProjection:
    """Projection policy interface.  It controls eligible supplier offers only."""

    @classmethod
    def require_scope(cls, tenant_scope: TenantScope) -> None:
        raise NotImplementedError

    @classmethod
    def eligible_offer_conditions(cls):
        raise NotImplementedError


class SystemCatalogDecisionProjection(CatalogDecisionProjection):
    """Canonical MVN policy: every active mapped supplier offer is eligible."""

    @classmethod
    def require_scope(cls, tenant_scope: TenantScope) -> None:
        if not tenant_scope.is_system:
            raise CatalogDecisionScopeError("System catalog projection cannot be used for tenant scope")

    @classmethod
    def eligible_offer_conditions(cls):
        return (
            ProductSupplierMapping.is_active.is_(True),
            SupplierOffer.is_active.is_(True),
            Supplier.is_active.is_(True),
        )


class CatalogDecisionQueryService:
    """A two-query (rate + count/page) projection with metrics before pagination."""

    _CATEGORY_SLUGS = {
        "household": "cat-household",
        "multi": "cat-multi",
        "semi_industrial": "cat-industrial",
    }

    @staticmethod
    def _json_float(session: AsyncSession, key: str):
        # The normalizer persists these canonical numeric keys.  The dialect
        # branch keeps unit tests on SQLite while production uses PostgreSQL.
        if session.bind is not None and session.bind.dialect.name == "sqlite":
            return cast(func.json_extract(Product.specs, f"$.{key}"), Float)
        from sqlalchemy.dialects.postgresql import JSONB
        return cast(func.jsonb_extract_path_text(cast(Product.specs, JSONB), key), Float)

    @staticmethod
    def _json_text(session: AsyncSession, key: str):
        if session.bind is not None and session.bind.dialect.name == "sqlite":
            return func.json_extract(Product.specs, f"$.{key}")
        from sqlalchemy.dialects.postgresql import JSONB
        return func.jsonb_extract_path_text(cast(Product.specs, JSONB), key)

    @classmethod
    def _metrics_cte(cls, *, usd_byn_rate: Decimal | None):
        cost = case(
            (SupplierOffer.wholesale_currency == "BYN", SupplierOffer.wholesale_value),
            (and_(SupplierOffer.wholesale_currency == "USD", usd_byn_rate is not None), SupplierOffer.wholesale_value * usd_byn_rate),
            else_=None,
        )
        active = SystemCatalogDecisionProjection.eligible_offer_conditions()
        # Cost follows the existing manager semantics: prefer an in-stock offer,
        # otherwise use the cheapest currently known active offer.
        in_stock_cost = func.min(case((SupplierOffer.qty > 0, cost), else_=None))
        any_cost = func.min(cost)
        return (
            select(
                ProductSupplierMapping.product_id.label("product_id"),
                func.coalesce(in_stock_cost, any_cost).label("purchase_cost_byn"),
                func.min(SupplierOffer.rrc_byn).label("recommended_price_byn"),
                func.min(Supplier.name).label("supplier_name"),
                func.coalesce(func.sum(SupplierOffer.qty), 0).label("supplier_qty"),
            )
            .select_from(ProductSupplierMapping)
            .join(
                SupplierOffer,
                and_(
                    SupplierOffer.supplier_id == ProductSupplierMapping.supplier_id,
                    SupplierOffer.external_id == ProductSupplierMapping.external_id,
                ),
            )
            .join(Supplier, Supplier.id == SupplierOffer.supplier_id)
            .where(*active)
            .group_by(ProductSupplierMapping.product_id)
            .cte("catalog_decision_metrics")
        )

    @staticmethod
    def _local_stock_cte():
        return (
            select(
                ProductLocalStock.product_id.label("product_id"),
                func.coalesce(func.sum(ProductLocalStock.qty), 0).label("local_qty"),
            )
            .group_by(ProductLocalStock.product_id)
            .cte("catalog_decision_local_stock")
        )

    @classmethod
    def _conditions(cls, session: AsyncSession, filters: CatalogDecisionFilters, *, availability, cooling_min, cooling_max):
        conditions = []
        search = (filters.search or "").strip()
        if search:
            pattern = f"%{search}%"
            conditions.append(or_(Product.title.ilike(pattern), Product.slug.ilike(pattern), Brand.title.ilike(pattern), ProductSeries.title.ilike(pattern)))
        if filters.cooling_min_kw is not None:
            conditions.append(cooling_max >= filters.cooling_min_kw)
        if filters.cooling_max_kw is not None:
            conditions.append(cooling_min <= filters.cooling_max_kw)
        area = ProductDAO.area_expr(session)
        if filters.area_min is not None:
            conditions.append(area >= filters.area_min)
        if filters.area_max is not None:
            conditions.append(area <= filters.area_max)
        if filters.category:
            conditions.append(exists(select(ProductTagLink.product_id).join(Tag, Tag.id == ProductTagLink.tag_id).where(ProductTagLink.product_id == Product.id, Tag.slug == cls._CATEGORY_SLUGS[filters.category])))
        if filters.indoor_form_factor:
            conditions.append(cls._json_text(session, "__filter_indoor_type") == filters.indoor_form_factor)
        if filters.brand_ids:
            conditions.append(Product.brand_id.in_(filters.brand_ids))
        if filters.series_ids:
            conditions.append(Product.series_id.in_(filters.series_ids))
        if filters.is_inverter is not None:
            conditions.append(Product.is_inverter.is_(filters.is_inverter))
        if filters.wifi:
            wifi = cls._json_text(session, "wifi_ready")
            if filters.wifi == "builtin":
                conditions.append(wifi.in_((True, "true", "True", "1")))
            elif filters.wifi == "ready":
                conditions.append(wifi == "ready")
            else:
                conditions.append(or_(wifi.is_(None), wifi.in_((False, "false", "False", "0"))))
        if filters.availability:
            conditions.append(availability == filters.availability)
        if filters.is_published is not None:
            conditions.append(Product.is_published.is_(filters.is_published))
        return conditions

    @classmethod
    async def list_system_products(
        cls, session: AsyncSession, *, tenant_scope: TenantScope, filters: CatalogDecisionFilters,
        page: int, limit: int, sort: str, direction: Literal["asc", "desc"],
    ) -> dict:
        SystemCatalogDecisionProjection.require_scope(tenant_scope)
        usd_byn_rate = await FxRateService.get_supplier_usd_byn_rate(session)
        metrics = cls._metrics_cte(usd_byn_rate=usd_byn_rate)
        local_stock = cls._local_stock_cte()
        purchase = metrics.c.purchase_cost_byn
        retail = cast(Product.price, Float)
        margin_abs = case((purchase.is_not(None), retail - purchase), else_=None).label("margin_abs_byn")
        margin_pct = case((and_(purchase.is_not(None), retail > 0), (retail - purchase) / retail), else_=None).label("margin_pct")
        total_qty = func.coalesce(metrics.c.supplier_qty, 0) + func.coalesce(local_stock.c.local_qty, 0)
        availability = case((total_qty > 0, "in_stock"), else_="out_of_stock").label("availability")
        cooling_nominal = func.coalesce(Product.power_cooling, cls._json_float(session, "capacity_cooling_kw")).label("cooling_power_kw")
        cooling_min = func.coalesce(cls._json_float(session, "capacity_cooling_min_kw"), cooling_nominal).label("cooling_min_kw")
        cooling_max = func.coalesce(cls._json_float(session, "capacity_cooling_max_kw"), cooling_nominal).label("cooling_max_kw")
        conditions = cls._conditions(session, filters, availability=availability, cooling_min=cooling_min, cooling_max=cooling_max)
        base = (
            select(
                Product, Brand.title.label("brand_title"), ProductSeries.title.label("series_title"),
                purchase, metrics.c.recommended_price_byn, metrics.c.supplier_name, metrics.c.supplier_qty,
                margin_abs, margin_pct, availability, cooling_nominal, cooling_min, cooling_max,
                ProductDAO.area_expr(session).label("area_m2"),
                cls._json_text(session, "__filter_indoor_type").label("indoor_form_factor"),
                cls._json_text(session, "wifi_ready").label("wifi_raw"),
            )
            .select_from(Product)
            .outerjoin(Brand, Brand.id == Product.brand_id)
            .outerjoin(ProductSeries, ProductSeries.id == Product.series_id)
            .outerjoin(metrics, metrics.c.product_id == Product.id)
            .outerjoin(local_stock, local_stock.c.product_id == Product.id)
            .where(*conditions)
        )
        sort_columns = {
            "retail_price": retail, "purchase_cost": purchase, "rrc": metrics.c.recommended_price_byn,
            "margin_abs": margin_abs, "margin_pct": margin_pct, "availability": availability,
            "cooling_power": cooling_nominal, "title": Product.title,
        }
        sort_column = sort_columns[sort]
        order_value = sort_column.asc() if direction == "asc" else sort_column.desc()
        # Nulls are always last, and product id makes every page boundary stable.
        rows = list((await session.execute(base.order_by(sort_column.is_(None).asc(), order_value, Product.id.asc()).offset((page - 1) * limit).limit(limit))).all())
        count = int((await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
        items = []
        for row in rows:
            product = row[0]
            wifi_raw = row.wifi_raw
            wifi = "builtin" if wifi_raw in (True, "true", "True", "1") else "ready" if wifi_raw == "ready" else "none"
            category = None
            # Category is a display hint only; filtering remains the canonical tag EXISTS above.
            items.append({
                "id": product.id, "title": product.title, "slug": product.slug, "main_image": product.main_image,
                "brand_title": row.brand_title, "series_title": row.series_title, "retail_price_byn": float(product.price),
                "purchase_cost_byn": float(row.purchase_cost_byn) if row.purchase_cost_byn is not None else None,
                "recommended_price_byn": float(row.recommended_price_byn) if row.recommended_price_byn is not None else None,
                "margin_abs_byn": round(float(row.margin_abs_byn), 2) if row.margin_abs_byn is not None else None,
                "margin_pct": round(float(row.margin_pct), 4) if row.margin_pct is not None else None,
                "supplier_name": row.supplier_name, "supplier_qty": int(row.supplier_qty or 0), "availability": row.availability,
                "cooling_power_kw": float(row.cooling_power_kw) if row.cooling_power_kw is not None else None,
                "cooling_min_kw": float(row.cooling_min_kw) if row.cooling_min_kw is not None else None,
                "cooling_max_kw": float(row.cooling_max_kw) if row.cooling_max_kw is not None else None,
                "area_m2": float(row.area_m2) if row.area_m2 is not None else None, "category": category,
                "indoor_form_factor": row.indoor_form_factor, "is_inverter": bool(product.is_inverter), "wifi": wifi,
                "is_published": bool(product.is_published),
            })
        total = count
        return {"items": items, "meta": {"page": page, "limit": limit, "total": total, "pages": max(1, (total + limit - 1) // limit)}}

    @classmethod
    async def list_system_filter_options(cls, session: AsyncSession, *, tenant_scope: TenantScope) -> dict:
        """Small master-catalog dictionaries for the workspace filter controls."""
        SystemCatalogDecisionProjection.require_scope(tenant_scope)
        brands = list((await session.execute(
            select(Brand.id, Brand.title)
            .join(Product, Product.brand_id == Brand.id)
            .group_by(Brand.id, Brand.title)
            .order_by(Brand.title.asc())
        )).all())
        series = list((await session.execute(
            select(ProductSeries.id, ProductSeries.title)
            .join(Product, Product.series_id == ProductSeries.id)
            .group_by(ProductSeries.id, ProductSeries.title)
            .order_by(ProductSeries.title.asc())
        )).all())
        return {
            "brands": [{"id": int(item.id), "title": item.title} for item in brands],
            "series": [{"id": int(item.id), "title": item.title} for item in series],
        }
