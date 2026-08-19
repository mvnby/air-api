from datetime import datetime

from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import (
    Brand,
    Feature,
    FeatureBrandLink,
    FeatureProductLink,
    FeatureSeriesLink,
    Product,
    ProductSeries,
    ProductCollection,
    ProductCollectionItem,
    ProductCollectionPlacement,
)
from models.tenancy import TenantScope
from services.tenant_scope_service import storefront_scope_clause


class ProductCollectionDAO:
    @staticmethod
    async def list_rule_option_rows(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        allowed_product_ids: set[int] | None = None,
    ) -> dict[str, list]:
        brand_statement = select(Brand)
        series_statement = select(ProductSeries)
        feature_statement = select(Feature).where(
            Feature.is_active.is_(True),
            Feature.archived_at.is_(None),
        )
        if not tenant_scope.is_system:
            allowed_ids = tuple(sorted(allowed_product_ids or set()))
            if not allowed_ids:
                return {"brands": [], "series": [], "features": []}
            allowed_brand_ids = select(Product.brand_id).where(
                Product.id.in_(allowed_ids),
                Product.brand_id.is_not(None),
            )
            allowed_series_ids = select(Product.series_id).where(
                Product.id.in_(allowed_ids),
                Product.series_id.is_not(None),
            )
            brand_statement = brand_statement.where(
                Brand.id.in_(allowed_brand_ids)
            )
            series_statement = series_statement.where(
                ProductSeries.id.in_(allowed_series_ids)
            )
            feature_statement = feature_statement.where(
                or_(
                    Feature.id.in_(
                        select(FeatureProductLink.feature_id).where(
                            FeatureProductLink.product_id.in_(allowed_ids),
                            FeatureProductLink.is_enabled.is_(True),
                        )
                    ),
                    Feature.id.in_(
                        select(FeatureBrandLink.feature_id).where(
                            FeatureBrandLink.brand_id.in_(allowed_brand_ids),
                            FeatureBrandLink.is_enabled.is_(True),
                        )
                    ),
                    Feature.id.in_(
                        select(FeatureSeriesLink.feature_id).where(
                            FeatureSeriesLink.series_id.in_(allowed_series_ids),
                            FeatureSeriesLink.is_enabled.is_(True),
                        )
                    ),
                )
            )
        brands = list(
            (
                await session.execute(
                    brand_statement.order_by(Brand.title.asc(), Brand.id.asc())
                )
            ).scalars().all()
        )
        series = list(
            (
                await session.execute(
                    series_statement.order_by(
                        ProductSeries.title.asc(),
                        ProductSeries.id.asc(),
                    )
                )
            ).scalars().all()
        )
        features = list(
            (
                await session.execute(
                    feature_statement.order_by(Feature.name.asc(), Feature.id.asc())
                )
            ).scalars().all()
        )
        return {"brands": brands, "series": series, "features": features}

    @staticmethod
    async def list_all(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> list[ProductCollection]:
        result = await session.execute(
            select(ProductCollection)
            .where(storefront_scope_clause(ProductCollection, tenant_scope))
            .options(
                selectinload(ProductCollection.items).selectinload(ProductCollectionItem.product),
                selectinload(ProductCollection.placements),
            )
            .order_by(ProductCollection.updated_at.desc(), ProductCollection.id.desc())
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().unique().all())

    @staticmethod
    async def get(
        session: AsyncSession,
        collection_id: int,
        *,
        tenant_scope: TenantScope,
        for_update: bool = False,
    ) -> ProductCollection | None:
        statement = (
            select(ProductCollection)
            .where(
                ProductCollection.id == collection_id,
                storefront_scope_clause(ProductCollection, tenant_scope),
            )
            .options(
                selectinload(ProductCollection.items).selectinload(ProductCollectionItem.product),
                selectinload(ProductCollection.placements),
            )
            .execution_options(populate_existing=True)
        )
        if for_update and session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(of=ProductCollection)
        result = await session.execute(statement)
        return result.scalars().unique().one_or_none()

    @staticmethod
    async def get_by_slug(
        session: AsyncSession,
        slug: str,
        *,
        tenant_scope: TenantScope,
    ) -> ProductCollection | None:
        result = await session.execute(
            select(ProductCollection).where(
                ProductCollection.slug == slug,
                storefront_scope_clause(ProductCollection, tenant_scope),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_placements(
        session: AsyncSession,
        *,
        surface_key: str,
        slot_key: str,
        now: datetime,
        tenant_scope: TenantScope,
    ) -> list[tuple[ProductCollectionPlacement, ProductCollection]]:
        result = await session.execute(
            select(ProductCollectionPlacement, ProductCollection)
            .join(
                ProductCollection,
                (ProductCollection.id == ProductCollectionPlacement.collection_id)
                & (ProductCollection.tenant_id == ProductCollectionPlacement.tenant_id)
                & (
                    ProductCollection.storefront_id
                    == ProductCollectionPlacement.storefront_id
                ),
            )
            .where(
                ProductCollectionPlacement.surface_key == surface_key,
                ProductCollectionPlacement.slot_key == slot_key,
                storefront_scope_clause(ProductCollectionPlacement, tenant_scope),
                storefront_scope_clause(ProductCollection, tenant_scope),
                ProductCollectionPlacement.is_enabled.is_(True),
                ProductCollection.status == "published",
                (ProductCollection.starts_at.is_(None) | (ProductCollection.starts_at <= now)),
                (ProductCollection.ends_at.is_(None) | (ProductCollection.ends_at > now)),
                (
                    ProductCollectionPlacement.starts_at.is_(None)
                    | (ProductCollectionPlacement.starts_at <= now)
                ),
                (
                    ProductCollectionPlacement.ends_at.is_(None)
                    | (ProductCollectionPlacement.ends_at > now)
                ),
            )
            .order_by(
                ProductCollectionPlacement.position.asc(),
                ProductCollectionPlacement.id.asc(),
            )
        )
        return list(result.all())

    @staticmethod
    async def list_items(
        session: AsyncSession,
        collection_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> list[ProductCollectionItem]:
        result = await session.execute(
            select(ProductCollectionItem)
            .where(
                ProductCollectionItem.collection_id == collection_id,
                storefront_scope_clause(ProductCollectionItem, tenant_scope),
            )
            .order_by(ProductCollectionItem.position.asc(), ProductCollectionItem.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def replace_items(
        session: AsyncSession,
        *,
        collection_id: int,
        tenant_scope: TenantScope,
        items: list[dict],
    ) -> None:
        await session.execute(
            delete(ProductCollectionItem).where(
                ProductCollectionItem.collection_id == collection_id,
                storefront_scope_clause(ProductCollectionItem, tenant_scope),
            )
        )
        await session.flush()
        for position, payload in enumerate(items):
            session.add(
                ProductCollectionItem(
                    tenant_id=tenant_scope.tenant_id,
                    storefront_id=tenant_scope.storefront_id,
                    collection_id=collection_id,
                    product_id=int(payload["product_id"]),
                    position=position,
                    is_pinned=bool(payload.get("is_pinned", True)),
                    editorial_note=payload.get("editorial_note"),
                )
            )
        await session.flush()

    @staticmethod
    async def replace_placements(
        session: AsyncSession,
        *,
        collection_id: int,
        tenant_scope: TenantScope,
        placements: list[dict],
    ) -> None:
        await session.execute(
            delete(ProductCollectionPlacement).where(
                ProductCollectionPlacement.collection_id == collection_id,
                storefront_scope_clause(ProductCollectionPlacement, tenant_scope),
            )
        )
        await session.flush()
        for payload in placements:
            session.add(
                ProductCollectionPlacement(
                    tenant_id=tenant_scope.tenant_id,
                    storefront_id=tenant_scope.storefront_id,
                    collection_id=collection_id,
                    **payload,
                )
            )
        await session.flush()
