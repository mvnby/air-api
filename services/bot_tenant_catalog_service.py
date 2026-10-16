"""Published partner offers only; an empty publication never expands to all products."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from models import Product, TenantOffer
from services.manager_tenant_catalog_service import ManagerTenantCatalogService
from services.product_serialization import sanitize_specs
from crud.product import ProductDAO


class BotTenantCatalogService:
    @staticmethod
    async def products(
        session: AsyncSession,
        scope,
        *,
        query: str | None = None,
        product_id: int | None = None,
        area: int | None = None,
        area_min: float | None = None,
        area_max: float | None = None,
        is_inverter: bool | None = None,
        tag_slugs: list[str] | None = None,
        limit: int = 10,
    ):
        conditions = [
            Product.is_published.is_(True),
            TenantOffer.status == "active",
            TenantOffer.is_published.is_(True),
        ]
        if product_id is not None:
            conditions.append(Product.id == product_id)
        if is_inverter is not None:
            conditions.append(Product.is_inverter == is_inverter)
        area_expr = ProductDAO.area_expr(session)
        if area_min is not None or area is not None:
            conditions.append(area_expr >= (area_min if area_min is not None else area))
        if area_max is not None:
            conditions.append(area_expr <= area_max)
        statement = (
            select(Product, TenantOffer)
            .join(TenantOffer, ManagerTenantCatalogService._offer_join(scope))
            .where(*conditions)
        )
        statement = ProductDAO._apply_common_filters(
            session, statement, tag_slugs=tag_slugs
        )
        if query:
            statement = ProductDAO._apply_smart_search_filter(
                session, statement, query.replace("%", "").replace("_", "")
            )
        rows = (
            await session.execute(
                statement.order_by(area_expr, TenantOffer.price, Product.id).limit(
                    min(limit, 100)
                )
            )
        ).all()
        result = []
        for product, offer in rows:
            specs = sanitize_specs(product.specs)
            product_area = specs.get("area_m2")
            result.append(
                dict(
                    id=int(product.id),
                    title=product.title,
                    slug=product.slug or "",
                    description=product.description or "",
                    price=int(offer.price),
                    specs={"area_m2": product_area},
                    power_cooling=product.power_cooling,
                    main_image=product.main_image,
                    categories=[],
                    vitebsk_qty=0,
                    minsk_qty=0,
                    availability_status="unknown",
                )
            )
            if len(result) >= limit:
                break
        return result
