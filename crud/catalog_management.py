"""One SQL selection shared by catalog pages and select-all snapshots."""

from dataclasses import fields

from sqlalchemy import Float, and_, case, cast, exists, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api_contracts.catalog_management import CatalogManagementFilters
from crud.product import ProductDAO
from models import Brand, Product, ProductSeries
from models.supplier import ProductLocalStock, ProductSupplierMapping, Supplier, SupplierOffer
from services.catalog_decision_projection import CatalogDecisionFilters, CatalogDecisionQueryService


class CatalogManagementDAO:
    @staticmethod
    def selection(session: AsyncSession, filters: CatalogManagementFilters):
        query = CatalogDecisionQueryService
        offers = (
            select(ProductSupplierMapping.product_id)
            .join(SupplierOffer, and_(SupplierOffer.supplier_id == ProductSupplierMapping.supplier_id, SupplierOffer.external_id == ProductSupplierMapping.external_id))
            .join(Supplier, Supplier.id == SupplierOffer.supplier_id)
            .where(ProductSupplierMapping.product_id == Product.id, ProductSupplierMapping.is_active.is_(True), SupplierOffer.is_active.is_(True), Supplier.is_active.is_(True))
        )
        if filters.supplier_id is not None:
            offers = offers.where(Supplier.id == filters.supplier_id)
        supplier_stock = exists(offers.where(SupplierOffer.qty > 0))
        local_stock = exists(select(ProductLocalStock.id).where(ProductLocalStock.product_id == Product.id, ProductLocalStock.qty > 0))
        available = supplier_stock if filters.supplier_id else or_(supplier_stock, local_stock)
        nominal = func.coalesce(Product.power_cooling, query._json_float(session, "capacity_cooling_kw"))
        canonical = CatalogDecisionFilters(**{key: value for key, value in filters.model_dump().items() if key in {item.name for item in fields(CatalogDecisionFilters)}})
        conditions = query._conditions(
            session, canonical,
            availability=case((available, "in_stock"), else_="out_of_stock"),
            retail=cast(Product.price, Float), cooling_nominal=nominal,
            cooling_min=func.coalesce(query._json_float(session, "capacity_cooling_min_kw"), nominal),
            cooling_max=func.coalesce(query._json_float(session, "capacity_cooling_max_kw"), nominal),
            area=query._json_float(session, "area_m2"),
            heating_min=func.coalesce(query._json_float_path(session, "__typed_specs", "temp_range_heat", "min"), query._json_float(session, "__filter_min_heat")),
        )
        stmt = select(Product.id).outerjoin(Brand, Brand.id == Product.brand_id).outerjoin(ProductSeries, ProductSeries.id == Product.series_id).where(*conditions)
        if filters.supplier_id is not None:
            stmt = stmt.where(exists(offers))
        if filters.category_missing:
            stmt = ProductDAO._apply_category_status_filter(stmt, "missing")
        missing = {
            "brand": Product.brand_id.is_(None),
            "series": Product.series_id.is_(None),
            "image": or_(Product.main_image.is_(None), Product.main_image == ""),
            "price": or_(Product.price.is_(None), Product.price <= 0),
        }
        if filters.missing:
            stmt = stmt.where(missing[filters.missing])
        return stmt

    @staticmethod
    def ordered(session, stmt, sort: str):
        if sort == "price_asc":
            return stmt.order_by(Product.price.asc(), Product.id.asc())
        if sort == "price_desc":
            return stmt.order_by(Product.price.desc(), Product.id.asc())
        if sort == "title":
            return stmt.order_by(Product.title.asc(), Product.id.asc())
        if sort == "recommended":
            return stmt.order_by(ProductDAO._catalog_recommendation_score_expr(session).desc(), Product.id.asc())
        return stmt.order_by(Product.created_at.desc(), Product.id.desc())
