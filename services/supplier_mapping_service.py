from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.supplier import (
    ProductLocalStockDAO,
    SupplierDAO,
    SupplierMappingDAO,
    SupplierOfferDAO,
    SupplierSourceDAO,
    SupplyProductDAO,
)
from models.product import Product
from models.supplier import ProductSupplierMapping


class SupplierCatalogService:
    @staticmethod
    async def list_suppliers(session: AsyncSession) -> dict:
        items = await SupplierDAO.list_suppliers(session)
        return {"items": items}

    @staticmethod
    async def create_supplier(session: AsyncSession, payload: dict):
        return await SupplierDAO.create_supplier(session, payload)

    @staticmethod
    async def update_supplier(session: AsyncSession, supplier_id: int, payload: dict):
        supplier = await SupplierDAO.get_supplier(session, supplier_id)
        if not supplier:
            return None
        return await SupplierDAO.update_supplier(session, supplier, payload)

    @staticmethod
    async def list_sources(session: AsyncSession) -> dict:
        items = await SupplierSourceDAO.list_sources(session)
        return {"items": items}

    @staticmethod
    async def create_source(session: AsyncSession, payload: dict):
        return await SupplierSourceDAO.create_source(session, payload)

    @staticmethod
    async def update_source(session: AsyncSession, source_id: int, payload: dict):
        source = await SupplierSourceDAO.get_source(session, source_id)
        if not source:
            return None
        return await SupplierSourceDAO.update_source(session, source, payload)

    @staticmethod
    async def delete_source(session: AsyncSession, source_id: int) -> bool:
        source = await SupplierSourceDAO.get_source(session, source_id)
        if not source:
            return False
        await SupplierSourceDAO.delete_source(session, source)
        return True


class SupplierMappingService:
    @staticmethod
    async def list_unmapped(
        session: AsyncSession,
        *,
        supplier_id: int | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        offset = (page - 1) * limit
        items, total = await SupplierOfferDAO.list_unmapped(
            session=session,
            supplier_id=supplier_id,
            limit=limit,
            offset=offset,
        )
        suppliers = await SupplierDAO.list_suppliers(session)
        supplier_map = {s.id: s for s in suppliers}
        data = []
        for offer in items:
            supplier = supplier_map.get(offer.supplier_id)
            data.append(
                {
                    "supplier_id": offer.supplier_id,
                    "supplier_name": supplier.name if supplier else None,
                    "external_id": offer.external_id,
                    "title_raw": offer.title_raw,
                    "qty": int(offer.qty or 0),
                    "qty_raw": offer.qty_raw,
                    "wholesale_raw": offer.wholesale_raw,
                    "wholesale_value": float(offer.wholesale_value) if offer.wholesale_value is not None else None,
                    "wholesale_currency": offer.wholesale_currency,
                    "rrc_raw": offer.rrc_raw,
                    "rrc_byn": float(offer.rrc_byn) if offer.rrc_byn is not None else None,
                    "is_active": offer.is_active,
                    "updated_at": offer.updated_at,
                }
            )
        return {
            "items": data,
            "meta": {
                "total": total,
                "page": page,
                "limit": limit,
                "pages": (total + limit - 1) // limit if limit else 1,
            },
        }

    @staticmethod
    async def create_mapping(
        session: AsyncSession,
        *,
        product_id: int,
        supplier_id: int,
        external_id: str,
        mapped_by: str | None = None,
    ):
        product_exists = await SupplyProductDAO.product_exists(session, product_id)
        if not product_exists:
            raise ValueError("Product not found")

        offer = await SupplierOfferDAO.get_by_key(session, supplier_id, external_id)
        if not offer:
            raise ValueError("Supplier offer not found")

        try:
            return await SupplierMappingDAO.create_mapping(
                session,
                {
                    "product_id": product_id,
                    "supplier_id": supplier_id,
                    "external_id": external_id,
                    "is_active": True,
                    "mapped_by": mapped_by,
                },
            )
        except IntegrityError as exc:
            await session.rollback()
            raise ValueError("This supplier offer is already mapped") from exc

    @staticmethod
    async def delete_mapping(session: AsyncSession, mapping_id: int) -> bool:
        mapping = await SupplierMappingDAO.get_mapping(session, mapping_id)
        if not mapping:
            return False
        await SupplierMappingDAO.delete_mapping(session, mapping)
        return True

    @staticmethod
    async def list_product_offers(session: AsyncSession, product_id: int) -> dict:
        offers = await SupplierOfferDAO.list_for_product(session, product_id)
        suppliers = await SupplierDAO.list_suppliers(session)
        supplier_map = {s.id: s for s in suppliers}
        mappings_res = await session.execute(
            select(ProductSupplierMapping).where(
                ProductSupplierMapping.product_id == product_id,
                ProductSupplierMapping.is_active.is_(True),
            )
        )
        mapping_map = {(m.supplier_id, m.external_id): m for m in mappings_res.scalars().all()}

        items = []
        for offer in offers:
            supplier = supplier_map.get(offer.supplier_id)
            mapping = mapping_map.get((offer.supplier_id, offer.external_id))
            items.append(
                {
                    "supplier_id": offer.supplier_id,
                    "supplier_name": supplier.name if supplier else None,
                    "external_id": offer.external_id,
                    "title_raw": offer.title_raw,
                    "qty": int(offer.qty or 0),
                    "qty_raw": offer.qty_raw,
                    "wholesale_raw": offer.wholesale_raw,
                    "wholesale_value": float(offer.wholesale_value) if offer.wholesale_value is not None else None,
                    "wholesale_currency": offer.wholesale_currency,
                    "rrc_raw": offer.rrc_raw,
                    "rrc_byn": float(offer.rrc_byn) if offer.rrc_byn is not None else None,
                    "is_active": offer.is_active,
                    "mapping_id": mapping.id if mapping else None,
                    "product_id": product_id,
                    "updated_at": offer.updated_at,
                }
            )
        return {"items": items, "meta": {"total": len(items), "page": 1, "limit": len(items) or 1, "pages": 1}}

    @staticmethod
    async def upsert_vitebsk_stock(
        session: AsyncSession,
        *,
        product_id: int,
        qty: int,
        updated_by: str | None,
    ):
        product = await session.get(Product, product_id)
        if not product:
            raise ValueError("Product not found")
        return await ProductLocalStockDAO.upsert(
            session=session,
            product_id=product_id,
            qty=qty,
            updated_by=updated_by,
            warehouse_code="vitebsk",
        )
