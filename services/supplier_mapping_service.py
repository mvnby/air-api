from __future__ import annotations

from datetime import datetime

from slugify import slugify
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
from models.supplier import ProductSupplierMapping, Supplier
from services.google_service import get_google_service
from services.supplier_match_service import suggest_products_for_offer


class SupplierCatalogService:
    @staticmethod
    def _extract_spreadsheet_id(value: str | None) -> tuple[str | None, str | None]:
        raw = (value or "").strip()
        if not raw:
            return None, None
        spreadsheet_id = get_google_service().extract_spreadsheet_id(raw)
        return spreadsheet_id, raw

    @staticmethod
    async def _ensure_unique_code(
        session: AsyncSession,
        name: str,
        requested_code: str | None = None,
        exclude_supplier_id: int | None = None,
    ) -> str:
        base = slugify((requested_code or "").strip()) if requested_code else ""
        if not base:
            base = slugify(name.strip()) or "supplier"
        candidate = base
        suffix = 2
        while True:
            stmt = select(Supplier.id).where(Supplier.code == candidate)
            if exclude_supplier_id is not None:
                stmt = stmt.where(Supplier.id != exclude_supplier_id)
            existing = (await session.execute(stmt.limit(1))).scalar_one_or_none()
            code_taken = existing is not None
            if not code_taken:
                return candidate
            candidate = f"{base}-{suffix}"
            suffix += 1

    @staticmethod
    async def list_suppliers(session: AsyncSession) -> dict:
        items = await SupplierDAO.list_suppliers(session)
        return {"items": items}

    @staticmethod
    async def create_supplier(session: AsyncSession, payload: dict):
        spreadsheet_id_or_url = payload.pop("spreadsheet_id_or_url", None)
        spreadsheet_id, spreadsheet_url = SupplierCatalogService._extract_spreadsheet_id(spreadsheet_id_or_url)
        payload["spreadsheet_id"] = spreadsheet_id
        payload["spreadsheet_url"] = spreadsheet_url
        payload["google_sheet_synced_at"] = datetime.now() if spreadsheet_id else None
        payload["code"] = await SupplierCatalogService._ensure_unique_code(
            session=session,
            name=payload.get("name") or "",
            requested_code=payload.get("code"),
        )
        return await SupplierDAO.create_supplier(session, payload)

    @staticmethod
    async def update_supplier(session: AsyncSession, supplier_id: int, payload: dict):
        supplier = await SupplierDAO.get_supplier(session, supplier_id)
        if not supplier:
            return None
        if "name" in payload and "code" not in payload:
            payload["code"] = await SupplierCatalogService._ensure_unique_code(
                session=session,
                name=payload.get("name") or supplier.name,
                requested_code=supplier.code,
                exclude_supplier_id=supplier_id,
            )
        if "code" in payload:
            payload["code"] = await SupplierCatalogService._ensure_unique_code(
                session=session,
                name=payload.get("name") or supplier.name,
                requested_code=payload.get("code"),
                exclude_supplier_id=supplier_id,
            )
        if "spreadsheet_id_or_url" in payload:
            spreadsheet_id, spreadsheet_url = SupplierCatalogService._extract_spreadsheet_id(
                payload.pop("spreadsheet_id_or_url")
            )
            payload["spreadsheet_id"] = spreadsheet_id
            payload["spreadsheet_url"] = spreadsheet_url
            payload["google_sheet_synced_at"] = datetime.now() if spreadsheet_id else None
        return await SupplierDAO.update_supplier(session, supplier, payload)

    @staticmethod
    async def list_sources(session: AsyncSession) -> dict:
        items = await SupplierSourceDAO.list_sources(session)
        suppliers = await SupplierDAO.list_suppliers(session)
        supplier_map = {s.id: s for s in suppliers}
        data = []
        for source in items:
            data.append(
                {
                    **source.model_dump(),
                    "supplier_name": supplier_map.get(source.supplier_id).name if supplier_map.get(source.supplier_id) else None,
                }
            )
        return {"items": data}

    @staticmethod
    async def list_supplier_sheets(session: AsyncSession, supplier_id: int) -> list[dict]:
        supplier = await SupplierDAO.get_supplier(session, supplier_id)
        if not supplier:
            raise ValueError("Supplier not found")
        if not supplier.spreadsheet_id:
            raise ValueError("Supplier spreadsheet is not set")
        return get_google_service().list_sheet_tabs(supplier.spreadsheet_id)

    @staticmethod
    async def _validate_sheet_name(session: AsyncSession, supplier_id: int, sheet_name: str | None) -> None:
        if not sheet_name:
            raise ValueError("sheet_name is required")
        tabs = await SupplierCatalogService.list_supplier_sheets(session, supplier_id)
        titles = {str(t.get("title") or "") for t in tabs}
        if sheet_name not in titles:
            raise ValueError(f"Sheet '{sheet_name}' not found in supplier spreadsheet")

    @staticmethod
    async def create_source(session: AsyncSession, payload: dict):
        supplier = await SupplierDAO.get_supplier(session, payload["supplier_id"])
        if not supplier:
            raise ValueError("Supplier not found")
        if not supplier.spreadsheet_id:
            raise ValueError("Supplier spreadsheet is not set")
        await SupplierCatalogService._validate_sheet_name(session, payload["supplier_id"], payload.get("sheet_name"))
        payload.pop("spreadsheet_id", None)
        return await SupplierSourceDAO.create_source(session, payload)

    @staticmethod
    async def update_source(session: AsyncSession, source_id: int, payload: dict):
        source = await SupplierSourceDAO.get_source(session, source_id)
        if not source:
            return None
        next_supplier_id = payload.get("supplier_id", source.supplier_id)
        if "sheet_name" in payload or "supplier_id" in payload:
            await SupplierCatalogService._validate_sheet_name(
                session,
                int(next_supplier_id),
                payload.get("sheet_name", source.sheet_name),
            )
        payload.pop("spreadsheet_id", None)
        return await SupplierSourceDAO.update_source(session, source, payload)

    @staticmethod
    async def delete_source(session: AsyncSession, source_id: int) -> bool:
        source = await SupplierSourceDAO.get_source(session, source_id)
        if not source:
            return False
        supplier_id = int(source.supplier_id)
        await SupplierOfferDAO.clear_source_reference(session, source_id)
        await session.commit()
        await SupplierSourceDAO.delete_source(session, source)
        remaining_sources = await SupplierSourceDAO.list_active_google_sources_for_supplier(
            session, supplier_id
        )
        # Rebuild supplier offers after source deletion to avoid stale rows in mapping UI.
        await SupplierOfferDAO.deactivate_all_for_supplier(session, supplier_id)
        await SupplierMappingDAO.deactivate_all_for_supplier(session, supplier_id)
        await session.commit()
        if remaining_sources:
            from services.supplier_sync_service import SupplierSyncService

            for remaining_source in remaining_sources:
                await SupplierSyncService.sync_source(session, remaining_source)
        return True

    @staticmethod
    async def delete_supplier(session: AsyncSession, supplier_id: int) -> bool:
        supplier = await SupplierDAO.get_supplier(session, supplier_id)
        if not supplier:
            return False
        await SupplierDAO.delete_supplier(session, supplier)
        return True


class SupplierMappingService:
    @staticmethod
    async def list_unmapped(
        session: AsyncSession,
        *,
        supplier_id: int | None = None,
        source_id: int | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> dict:
        offset = (page - 1) * limit
        items, total = await SupplierOfferDAO.list_unmapped(
            session=session,
            supplier_id=supplier_id,
            source_id=source_id,
            limit=limit,
            offset=offset,
        )
        suppliers = await SupplierDAO.list_suppliers(session)
        sources = await SupplierSourceDAO.list_sources(session)
        supplier_map = {s.id: s for s in suppliers}
        source_map = {s.id: s for s in sources}
        data = []
        for offer in items:
            supplier = supplier_map.get(offer.supplier_id)
            source = source_map.get(offer.source_id) if offer.source_id else None
            data.append(
                {
                    "supplier_id": offer.supplier_id,
                    "source_id": offer.source_id,
                    "source_name": source.sheet_name if source else None,
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
    async def create_bulk_mappings(
        session: AsyncSession,
        *,
        items: list[dict],
        mapped_by: str | None = None,
        skip_conflicts: bool = True,
    ) -> dict:
        created_count = 0
        skipped_count = 0
        errors: list[dict] = []
        for item in items:
            try:
                await SupplierMappingService.create_mapping(
                    session=session,
                    product_id=int(item["product_id"]),
                    supplier_id=int(item["supplier_id"]),
                    external_id=str(item["external_id"]),
                    mapped_by=mapped_by,
                )
                created_count += 1
            except Exception as exc:
                if skip_conflicts:
                    skipped_count += 1
                    errors.append(
                        {
                            "supplier_id": item.get("supplier_id"),
                            "external_id": item.get("external_id"),
                            "message": str(exc),
                        }
                    )
                    continue
                raise
        return {
            "created_count": created_count,
            "skipped_count": skipped_count,
            "errors": errors,
        }

    @staticmethod
    async def suggest_for_offers(
        session: AsyncSession,
        *,
        items: list[dict],
        limit_per_offer: int = 5,
    ) -> dict:
        out = []
        for item in items:
            result = await suggest_products_for_offer(
                session=session,
                title_raw=item.get("title_raw"),
                limit=limit_per_offer,
            )
            out.append(
                {
                    "supplier_id": item.get("supplier_id"),
                    "external_id": item.get("external_id"),
                    **result,
                }
            )
        return {"items": out}

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
        sources = await SupplierSourceDAO.list_sources(session)
        supplier_map = {s.id: s for s in suppliers}
        source_map = {s.id: s for s in sources}
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
            source = source_map.get(offer.source_id) if offer.source_id else None
            mapping = mapping_map.get((offer.supplier_id, offer.external_id))
            items.append(
                {
                    "supplier_id": offer.supplier_id,
                    "source_id": offer.source_id,
                    "source_name": source.sheet_name if source else None,
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
