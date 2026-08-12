from __future__ import annotations

from sqlalchemy import String, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.product import Product
from models.supplier import ProductSupplierMapping, Supplier, SupplierOffer, SupplierPriceSource


def _escaped_contains(column, value: str):
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


class SupplierOfferMappingDAO:
    @staticmethod
    async def list_candidates(
        session: AsyncSession,
        *,
        supplier_id: int,
        source_id: int | None,
        query: str | None,
        include_inactive: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple], int]:
        filters = [SupplierOffer.supplier_id == supplier_id]
        if source_id is not None:
            filters.append(SupplierOffer.source_id == source_id)
        if not include_inactive:
            filters.append(SupplierOffer.is_active.is_(True))
        if query:
            filters.append(
                or_(
                    _escaped_contains(SupplierOffer.external_id, query),
                    _escaped_contains(SupplierOffer.title_raw, query),
                    _escaped_contains(SupplierOffer.title_normalized, query),
                    _escaped_contains(cast(SupplierOffer.model_tokens, String), query),
                    _escaped_contains(cast(SupplierOffer.indoor_model_tokens, String), query),
                    _escaped_contains(cast(SupplierOffer.outdoor_model_tokens, String), query),
                )
            )

        count_stmt = select(func.count()).select_from(SupplierOffer).where(*filters)
        total = int((await session.execute(count_stmt)).scalar_one())
        stmt = (
            select(
                SupplierOffer,
                Supplier.name,
                SupplierPriceSource.sheet_name,
                ProductSupplierMapping,
                Product.title,
                Product.slug,
            )
            .join(Supplier, Supplier.id == SupplierOffer.supplier_id)
            .outerjoin(SupplierPriceSource, SupplierPriceSource.id == SupplierOffer.source_id)
            .outerjoin(
                ProductSupplierMapping,
                (ProductSupplierMapping.supplier_id == SupplierOffer.supplier_id)
                & (ProductSupplierMapping.external_id == SupplierOffer.external_id),
            )
            .outerjoin(Product, Product.id == ProductSupplierMapping.product_id)
            .where(*filters)
            .order_by(SupplierOffer.updated_at.desc(), SupplierOffer.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list((await session.execute(stmt)).all()), total

    @staticmethod
    async def lock_offer(session: AsyncSession, offer_id: int) -> SupplierOffer | None:
        result = await session.execute(
            select(SupplierOffer).where(SupplierOffer.id == offer_id).with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def lock_mapping_for_offer(
        session: AsyncSession,
        *,
        supplier_id: int,
        external_id: str,
    ) -> ProductSupplierMapping | None:
        result = await session.execute(
            select(ProductSupplierMapping)
            .where(
                ProductSupplierMapping.supplier_id == supplier_id,
                ProductSupplierMapping.external_id == external_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def lock_product(session: AsyncSession, product_id: int) -> Product | None:
        result = await session.execute(
            select(Product).where(Product.id == product_id).with_for_update()
        )
        return result.scalar_one_or_none()
