from __future__ import annotations

from sqlalchemy import and_, exists, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Brand, Product, ProductSeries, TenantCatalogGrant, TenantOffer
from models.tenancy import TenantScope


class ManagerTenantCatalogService:
    """Expose a published, supplier-free catalog projection to tenant managers."""

    @staticmethod
    def _conditions(*, search: str | None, allowed: bool | None, tenant_scope: TenantScope):
        conditions = [Product.is_published.is_(True)]
        normalized_search = str(search or "").strip()
        if normalized_search:
            pattern = f"%{normalized_search}%"
            conditions.append(
                or_(
                    Product.title.ilike(pattern),
                    Product.slug.ilike(pattern),
                    Brand.title.ilike(pattern),
                    ProductSeries.title.ilike(pattern),
                )
            )
        if allowed is not None and not tenant_scope.is_system:
            offer_is_allowed = and_(
                TenantOffer.id.is_not(None),
                TenantOffer.status == "active",
                TenantOffer.is_published.is_(True),
            )
            conditions.append(offer_is_allowed if allowed else ~offer_is_allowed)
        return conditions

    @staticmethod
    def _offer_join(tenant_scope: TenantScope):
        exact_scope = and_(
            TenantOffer.product_id == Product.id,
            TenantOffer.tenant_id == tenant_scope.tenant_id,
            TenantOffer.storefront_id == tenant_scope.storefront_id,
        )
        if tenant_scope.is_system:
            return exact_scope
        active_grant = exists(
            select(TenantCatalogGrant.id).where(
                TenantCatalogGrant.id == TenantOffer.catalog_grant_id,
                TenantCatalogGrant.tenant_id == tenant_scope.tenant_id,
                TenantCatalogGrant.storefront_id == tenant_scope.storefront_id,
                TenantCatalogGrant.status == "active",
            )
        )
        return and_(
            exact_scope,
            or_(
                TenantOffer.catalog_grant_id.is_(None),
                active_grant,
            ),
        )

    @classmethod
    async def list_products(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        page: int,
        limit: int,
        search: str | None,
        allowed: bool | None,
    ) -> dict:
        conditions = cls._conditions(
            search=search,
            allowed=allowed,
            tenant_scope=tenant_scope,
        )
        joins = (
            (Brand, Brand.id == Product.brand_id),
            (ProductSeries, ProductSeries.id == Product.series_id),
        )
        statement = (
            select(Product, Brand.title, ProductSeries.title, TenantOffer)
            .outerjoin(*joins[0])
            .outerjoin(*joins[1])
            .outerjoin(TenantOffer, cls._offer_join(tenant_scope))
            .where(*conditions)
            .order_by(Product.title.asc(), Product.id.asc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = list((await session.execute(statement)).all())

        count_statement = (
            select(func.count(Product.id))
            .select_from(Product)
            .outerjoin(*joins[0])
            .outerjoin(*joins[1])
            .outerjoin(TenantOffer, cls._offer_join(tenant_scope))
            .where(*conditions)
        )
        total = int((await session.execute(count_statement)).scalar_one())
        pages = (total + limit - 1) // limit if total else 1

        items = []
        for product, brand_title, series_title, offer in rows:
            offer_allowed = bool(
                offer is not None
                and offer.status == "active"
                and offer.is_published
            )
            item_allowed = bool(product.is_published) if tenant_scope.is_system else offer_allowed
            effective_price = (
                int(product.price)
                if tenant_scope.is_system
                else int(offer.price)
                if offer_allowed
                else None
            )
            items.append(
                {
                    "id": int(product.id),
                    "title": product.title,
                    "slug": product.slug,
                    "brand_title": brand_title,
                    "series_title": series_title,
                    "main_image": product.main_image,
                    "product_kind": product.product_kind,
                    "is_inverter": bool(product.is_inverter),
                    "power_cooling": product.power_cooling,
                    "offer_id": int(offer.id) if offer is not None else None,
                    "offer_status": offer.status if offer is not None else None,
                    "offer_is_published": bool(offer.is_published) if offer is not None else None,
                    "effective_price": effective_price,
                    "allowed": item_allowed,
                }
            )
        return {
            "items": items,
            "meta": {"page": page, "limit": limit, "total": total, "pages": pages},
        }
