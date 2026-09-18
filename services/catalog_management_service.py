from itertools import islice

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api_contracts.catalog_management import CatalogManagementFilters, CatalogManagementQuery
from crud.catalog_management import CatalogManagementDAO
from crud.product import ProductDAO
from models import Product
from services.feature_resolver_service import FeatureResolverService
from services.product_manager_service import ProductManagerService
from services.product_supply_metrics_service import ProductSupplyMetricsService
from services.yandex_business_price_list_service import YandexBusinessPriceListService


class CatalogManagementService:
    @staticmethod
    def _uses_expensive_filters(filters: CatalogManagementFilters) -> bool:
        return filters.feature_id is not None or filters.in_yandex_feed is not None

    @staticmethod
    async def _filtered_ordered_ids(
        session: AsyncSession,
        ordered_stmt,
        filters: CatalogManagementFilters,
        *,
        stop_after: int | None = None,
    ) -> list[int]:
        """Apply resolver-backed filters in bounded product batches after SQL narrowing."""
        feed_ids = (
            await YandexBusinessPriceListService.current_product_offer_ids(session)
            if filters.in_yandex_feed is not None
            else None
        )
        candidate_ids = (await session.execute(ordered_stmt)).scalars()
        matched: list[int] = []
        while chunk := list(islice(candidate_ids, 200)):
            products = list((await session.execute(
                select(Product).where(Product.id.in_(chunk))
            )).scalars().all())
            by_id = {int(product.id): product for product in products if product.id is not None}
            resolved = (
                await FeatureResolverService.resolve_for_products(session, products)
                if filters.feature_id is not None
                else {}
            )
            for product_id in chunk:
                product = by_id.get(int(product_id))
                if product is None:
                    continue
                if feed_ids is not None and (int(product_id) in feed_ids) != filters.in_yandex_feed:
                    continue
                if filters.feature_id is not None:
                    effective_ids = {
                        int(feature.id)
                        for feature in resolved.get(int(product_id), {}).get("effective", [])
                    }
                    if (filters.feature_id in effective_ids) != filters.has_feature:
                        continue
                matched.append(int(product_id))
                if stop_after is not None and len(matched) >= stop_after:
                    return matched
        return matched

    @staticmethod
    async def query(session: AsyncSession, payload: CatalogManagementQuery) -> dict:
        stmt = CatalogManagementDAO.selection(session, payload.filters)
        ordered = CatalogManagementDAO.ordered(session, stmt, payload.sort)
        if CatalogManagementService._uses_expensive_filters(payload.filters):
            all_ids = await CatalogManagementService._filtered_ordered_ids(session, ordered, payload.filters)
            total = len(all_ids)
            start = (payload.page - 1) * payload.limit
            ids = all_ids[start:start + payload.limit]
        else:
            total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
            ids = list((await session.execute(ordered.offset((payload.page - 1) * payload.limit).limit(payload.limit))).scalars().all())
        products = await ProductDAO.get_by_ids(session, ids)
        by_id = {product.id: product for product in products}
        supply = await ProductSupplyMetricsService.compute_for_products(session, products)
        return {
            "items": [ProductManagerService._serialize_manager_product(by_id[pid], supply.get(pid, {})) for pid in ids],
            "meta": {"page": payload.page, "limit": payload.limit, "total": total, "pages": (total + payload.limit - 1) // payload.limit},
        }

    @staticmethod
    async def selection(session: AsyncSession, filters: CatalogManagementFilters) -> dict:
        stmt = CatalogManagementDAO.selection(session, filters).order_by(Product.id.asc())
        if CatalogManagementService._uses_expensive_filters(filters):
            ids = await CatalogManagementService._filtered_ordered_ids(
                session, stmt, filters, stop_after=501,
            )
        else:
            ids = list((await session.execute(stmt.limit(501))).scalars().all())
        if len(ids) > 500:
            raise ValueError("Для одного изменения выберите не более 500 товаров. Уточните фильтры.")
        return {"product_ids": ids, "total": len(ids)}
