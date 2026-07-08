from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import and_, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.product import Product
from models.supplier import (
    ProductLocalStock,
    ProductSupplierMapping,
    Supplier,
    SupplierContact,
    SupplierOffer,
    SupplierPriceSource,
    SupplierSyncRun,
    SupplierWarehouse,
    SupplyRequest,
    SupplyRequestLine,
)


class SupplierDAO:
    @staticmethod
    async def list_suppliers(session: AsyncSession) -> list[Supplier]:
        result = await session.execute(select(Supplier).order_by(Supplier.priority.asc(), Supplier.name.asc()))
        return list(result.scalars().all())

    @staticmethod
    async def get_supplier(session: AsyncSession, supplier_id: int) -> Optional[Supplier]:
        return await session.get(Supplier, supplier_id)

    @staticmethod
    async def create_supplier(session: AsyncSession, payload: dict) -> Supplier:
        obj = Supplier(**payload)
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return obj

    @staticmethod
    async def update_supplier(session: AsyncSession, supplier: Supplier, payload: dict) -> Supplier:
        for key, value in payload.items():
            setattr(supplier, key, value)
        supplier.updated_at = datetime.now()
        session.add(supplier)
        await session.commit()
        await session.refresh(supplier)
        return supplier

    @staticmethod
    async def delete_supplier(session: AsyncSession, supplier: Supplier) -> None:
        await session.execute(
            delete(SupplyRequestLine).where(
                SupplyRequestLine.request_id.in_(
                    select(SupplyRequest.id).where(SupplyRequest.supplier_id == supplier.id)
                )
            )
        )
        await session.execute(
            delete(SupplyRequest).where(SupplyRequest.supplier_id == supplier.id)
        )
        await session.execute(
            delete(SupplierWarehouse).where(SupplierWarehouse.supplier_id == supplier.id)
        )
        await session.execute(
            delete(SupplierContact).where(SupplierContact.supplier_id == supplier.id)
        )
        await session.execute(
            delete(ProductSupplierMapping).where(ProductSupplierMapping.supplier_id == supplier.id)
        )
        await session.execute(
            delete(SupplierOffer).where(SupplierOffer.supplier_id == supplier.id)
        )
        await session.execute(
            delete(SupplierSyncRun).where(
                SupplierSyncRun.source_id.in_(
                    select(SupplierPriceSource.id).where(SupplierPriceSource.supplier_id == supplier.id)
                )
            )
        )
        await session.execute(
            delete(SupplierPriceSource).where(SupplierPriceSource.supplier_id == supplier.id)
        )
        await session.delete(supplier)
        await session.commit()


class SupplierSourceDAO:
    @staticmethod
    async def list_sources(session: AsyncSession) -> list[SupplierPriceSource]:
        result = await session.execute(
            select(SupplierPriceSource).order_by(SupplierPriceSource.id.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_source(session: AsyncSession, source_id: int) -> Optional[SupplierPriceSource]:
        return await session.get(SupplierPriceSource, source_id)

    @staticmethod
    async def get_source_by_supplier_sheet(
        session: AsyncSession,
        supplier_id: int,
        sheet_name: str,
    ) -> Optional[SupplierPriceSource]:
        result = await session.execute(
            select(SupplierPriceSource).where(
                SupplierPriceSource.supplier_id == supplier_id,
                SupplierPriceSource.sheet_name == sheet_name,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_source(session: AsyncSession, payload: dict) -> SupplierPriceSource:
        obj = SupplierPriceSource(**payload)
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return obj

    @staticmethod
    async def update_source(session: AsyncSession, source: SupplierPriceSource, payload: dict) -> SupplierPriceSource:
        for key, value in payload.items():
            setattr(source, key, value)
        source.updated_at = datetime.now()
        session.add(source)
        await session.commit()
        await session.refresh(source)
        return source

    @staticmethod
    async def list_active_sync_sources(session: AsyncSession) -> list[SupplierPriceSource]:
        result = await session.execute(
            select(SupplierPriceSource).where(
                SupplierPriceSource.is_active.is_(True),
                SupplierPriceSource.source_type.in_(("google_sheet", "hisense_price_xlsx")),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_active_sync_sources_for_supplier(
        session: AsyncSession,
        supplier_id: int,
    ) -> list[SupplierPriceSource]:
        result = await session.execute(
            select(SupplierPriceSource).where(
                SupplierPriceSource.supplier_id == supplier_id,
                SupplierPriceSource.is_active.is_(True),
                SupplierPriceSource.source_type.in_(("google_sheet", "hisense_price_xlsx")),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_active_google_sources(session: AsyncSession) -> list[SupplierPriceSource]:
        return await SupplierSourceDAO.list_active_sync_sources(session)

    @staticmethod
    async def list_active_google_sources_for_supplier(
        session: AsyncSession,
        supplier_id: int,
    ) -> list[SupplierPriceSource]:
        return await SupplierSourceDAO.list_active_sync_sources_for_supplier(session, supplier_id)

    @staticmethod
    async def delete_source(session: AsyncSession, source: SupplierPriceSource) -> None:
        await session.execute(
            delete(SupplierSyncRun).where(SupplierSyncRun.source_id == source.id)
        )
        await session.delete(source)
        await session.commit()


class SupplierOfferDAO:
    @staticmethod
    async def get_by_key(session: AsyncSession, supplier_id: int, external_id: str) -> Optional[SupplierOffer]:
        result = await session.execute(
            select(SupplierOffer).where(
                SupplierOffer.supplier_id == supplier_id,
                SupplierOffer.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_offer(session: AsyncSession, payload: dict) -> SupplierOffer:
        existing = await SupplierOfferDAO.get_by_key(
            session=session,
            supplier_id=payload["supplier_id"],
            external_id=payload["external_id"],
        )
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.updated_at = datetime.now()
            session.add(existing)
            return existing

        obj = SupplierOffer(**payload)
        session.add(obj)
        return obj

    @staticmethod
    async def deactivate_missing_offers(
        session: AsyncSession,
        supplier_id: int,
        present_external_ids: set[str],
    ) -> int:
        result = await session.execute(
            select(SupplierOffer).where(
                SupplierOffer.supplier_id == supplier_id,
                SupplierOffer.is_active.is_(True),
            )
        )
        offers = list(result.scalars().all())
        deactivated = 0
        for offer in offers:
            if offer.external_id not in present_external_ids:
                offer.is_active = False
                offer.updated_at = datetime.now()
                session.add(offer)
                deactivated += 1
        return deactivated

    @staticmethod
    async def deactivate_all_for_supplier(session: AsyncSession, supplier_id: int) -> int:
        result = await session.execute(
            select(SupplierOffer).where(
                SupplierOffer.supplier_id == supplier_id,
                SupplierOffer.is_active.is_(True),
            )
        )
        offers = list(result.scalars().all())
        deactivated = 0
        for offer in offers:
            offer.is_active = False
            offer.updated_at = datetime.now()
            session.add(offer)
            deactivated += 1
        return deactivated

    @staticmethod
    async def clear_source_reference(session: AsyncSession, source_id: int) -> None:
        result = await session.execute(
            select(SupplierOffer).where(SupplierOffer.source_id == source_id)
        )
        offers = list(result.scalars().all())
        for offer in offers:
            offer.source_id = None
            offer.updated_at = datetime.now()
            session.add(offer)

    @staticmethod
    async def list_unmapped(
        session: AsyncSession,
        supplier_id: Optional[int] = None,
        source_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[SupplierOffer], int]:
        mapping_exists = (
            select(ProductSupplierMapping.id)
            .where(
                ProductSupplierMapping.supplier_id == SupplierOffer.supplier_id,
                ProductSupplierMapping.external_id == SupplierOffer.external_id,
                ProductSupplierMapping.is_active.is_(True),
            )
            .exists()
        )

        base = select(SupplierOffer).where(
            SupplierOffer.is_active.is_(True),
            ~mapping_exists,
        )
        count_stmt = select(func.count()).select_from(SupplierOffer).where(
            SupplierOffer.is_active.is_(True),
            ~mapping_exists,
        )
        if supplier_id is not None:
            base = base.where(SupplierOffer.supplier_id == supplier_id)
            count_stmt = count_stmt.where(SupplierOffer.supplier_id == supplier_id)
        if source_id is not None:
            base = base.where(SupplierOffer.source_id == source_id)
            count_stmt = count_stmt.where(SupplierOffer.source_id == source_id)

        total = (await session.execute(count_stmt)).scalar_one()
        result = await session.execute(
            base.order_by(SupplierOffer.updated_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), int(total)

    @staticmethod
    async def list_for_product(session: AsyncSession, product_id: int) -> list[SupplierOffer]:
        stmt = (
            select(SupplierOffer)
            .join(
                ProductSupplierMapping,
                and_(
                    ProductSupplierMapping.supplier_id == SupplierOffer.supplier_id,
                    ProductSupplierMapping.external_id == SupplierOffer.external_id,
                    ProductSupplierMapping.is_active.is_(True),
                ),
            )
            .where(ProductSupplierMapping.product_id == product_id)
            .order_by(SupplierOffer.updated_at.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


class SupplierMappingDAO:
    @staticmethod
    async def create_mapping(session: AsyncSession, payload: dict) -> ProductSupplierMapping:
        mapping = ProductSupplierMapping(**payload)
        session.add(mapping)
        await session.commit()
        await session.refresh(mapping)
        return mapping

    @staticmethod
    async def get_mapping(session: AsyncSession, mapping_id: int) -> Optional[ProductSupplierMapping]:
        return await session.get(ProductSupplierMapping, mapping_id)

    @staticmethod
    async def delete_mapping(session: AsyncSession, mapping: ProductSupplierMapping) -> None:
        await session.delete(mapping)
        await session.commit()

    @staticmethod
    async def deactivate_all_for_supplier(session: AsyncSession, supplier_id: int) -> int:
        result = await session.execute(
            select(ProductSupplierMapping).where(
                ProductSupplierMapping.supplier_id == supplier_id,
                ProductSupplierMapping.is_active.is_(True),
            )
        )
        mappings = list(result.scalars().all())
        deactivated = 0
        for mapping in mappings:
            mapping.is_active = False
            session.add(mapping)
            deactivated += 1
        return deactivated

    @staticmethod
    async def list_mappings_for_products(
        session: AsyncSession,
        product_ids: list[int],
    ) -> list[ProductSupplierMapping]:
        if not product_ids:
            return []
        result = await session.execute(
            select(ProductSupplierMapping).where(
                ProductSupplierMapping.product_id.in_(product_ids),
                ProductSupplierMapping.is_active.is_(True),
            )
        )
        return list(result.scalars().all())


class ProductLocalStockDAO:
    @staticmethod
    async def upsert(
        session: AsyncSession,
        product_id: int,
        qty: int,
        updated_by: Optional[str],
        warehouse_code: str = "vitebsk",
    ) -> ProductLocalStock:
        result = await session.execute(
            select(ProductLocalStock).where(
                ProductLocalStock.product_id == product_id,
                ProductLocalStock.warehouse_code == warehouse_code,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = ProductLocalStock(
                product_id=product_id,
                warehouse_code=warehouse_code,
                qty=qty,
                updated_by=updated_by,
            )
        else:
            row.qty = qty
            row.updated_by = updated_by
            row.updated_at = datetime.now()
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    @staticmethod
    async def list_for_products(
        session: AsyncSession,
        product_ids: list[int],
        warehouse_code: str = "vitebsk",
    ) -> list[ProductLocalStock]:
        if not product_ids:
            return []
        result = await session.execute(
            select(ProductLocalStock).where(
                ProductLocalStock.product_id.in_(product_ids),
                ProductLocalStock.warehouse_code == warehouse_code,
            )
        )
        return list(result.scalars().all())


class SupplierSyncRunDAO:
    @staticmethod
    async def create_run(session: AsyncSession, source_id: int) -> SupplierSyncRun:
        run = SupplierSyncRun(source_id=source_id)
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run

    @staticmethod
    async def finish_run(
        session: AsyncSession,
        run: SupplierSyncRun,
        *,
        status: str,
        rows_total: int,
        rows_upserted: int,
        rows_skipped: int,
        rows_deactivated: int,
        error: Optional[str] = None,
    ) -> SupplierSyncRun:
        run.status = status
        run.rows_total = rows_total
        run.rows_upserted = rows_upserted
        run.rows_skipped = rows_skipped
        run.rows_deactivated = rows_deactivated
        run.error = error
        run.finished_at = datetime.now()
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run


class SupplyProductDAO:
    @staticmethod
    async def product_exists(session: AsyncSession, product_id: int) -> bool:
        return await session.get(Product, product_id) is not None
