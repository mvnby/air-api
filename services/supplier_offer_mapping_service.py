from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from crud.supplier_offer_mapping import SupplierOfferMappingDAO
from models.product import Product
from models.supplier import ProductSupplierMapping


class SupplierOfferMappingConflictError(ValueError):
    pass


class SupplierOfferMappingService:
    @staticmethod
    async def list_candidates(
        session: AsyncSession,
        *,
        product_id: int,
        supplier_id: int,
        source_id: int | None = None,
        query: str | None = None,
        page: int = 1,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> dict:
        product = await session.get(Product, product_id)
        if product is None:
            raise ValueError("Product not found")

        normalized_query = " ".join((query or "").split()) or None
        rows, total = await SupplierOfferMappingDAO.list_candidates(
            session,
            supplier_id=supplier_id,
            source_id=source_id,
            query=normalized_query,
            include_inactive=include_inactive,
            limit=limit,
            offset=(page - 1) * limit,
        )
        items = []
        for offer, supplier_name, source_name, mapping, mapped_title, mapped_slug in rows:
            if not offer.is_active:
                status = "inactive"
            elif mapping is None or not mapping.is_active:
                status = "free"
            elif mapping.product_id == product_id:
                status = "current"
            else:
                status = "conflict"
            items.append(
                {
                    "offer_id": offer.id,
                    "supplier_id": offer.supplier_id,
                    "supplier_name": supplier_name,
                    "source_id": offer.source_id,
                    "source_name": source_name,
                    "external_id": offer.external_id,
                    "title_raw": offer.title_raw,
                    "title_normalized": offer.title_normalized,
                    "source_url": offer.source_url,
                    "model_tokens": offer.model_tokens or [],
                    "qty": int(offer.qty or 0),
                    "qty_raw": offer.qty_raw,
                    "wholesale_raw": offer.wholesale_raw,
                    "wholesale_value": (
                        float(offer.wholesale_value) if offer.wholesale_value is not None else None
                    ),
                    "wholesale_currency": offer.wholesale_currency,
                    "rrc_raw": offer.rrc_raw,
                    "rrc_byn": float(offer.rrc_byn) if offer.rrc_byn is not None else None,
                    "is_active": bool(offer.is_active),
                    "status": status,
                    "mapping_id": mapping.id if mapping else None,
                    "mapping_is_active": bool(mapping.is_active) if mapping else None,
                    "mapped_product_id": mapping.product_id if mapping else None,
                    "mapped_product_title": mapped_title,
                    "mapped_product_slug": mapped_slug,
                    "mapped_by": mapping.mapped_by if mapping else None,
                    "mapped_at": mapping.mapped_at if mapping else None,
                    "updated_at": offer.updated_at,
                }
            )
        return {
            "items": items,
            "meta": {
                "total": total,
                "page": page,
                "limit": limit,
                "pages": (total + limit - 1) // limit,
            },
        }

    @staticmethod
    def _validate_expected_state(
        *,
        mapping: ProductSupplierMapping | None,
        expected_mapping_id: int | None,
        expected_product_id: int | None,
    ) -> None:
        if (expected_mapping_id is None) != (expected_product_id is None):
            raise SupplierOfferMappingConflictError(
                "expected_mapping_id and expected_product_id must be provided together"
            )
        if expected_mapping_id is None:
            return
        if (
            mapping is None
            or mapping.id != expected_mapping_id
            or mapping.product_id != expected_product_id
            or not mapping.is_active
        ):
            raise SupplierOfferMappingConflictError("Supplier offer mapping changed concurrently")

    @staticmethod
    async def put_mapping(
        session: AsyncSession,
        *,
        offer_id: int,
        product_id: int,
        replace_existing: bool,
        expected_mapping_id: int | None,
        expected_product_id: int | None,
        mapped_by: str | None,
    ) -> dict:
        if replace_existing and (expected_mapping_id is None or expected_product_id is None):
            raise SupplierOfferMappingConflictError(
                "replace_existing requires expected_mapping_id and expected_product_id"
            )

        offer = await SupplierOfferMappingDAO.lock_offer(session, offer_id)
        if offer is None:
            raise ValueError("Supplier offer not found")
        if not offer.is_active:
            raise ValueError("Inactive supplier offer cannot be mapped")
        product = await SupplierOfferMappingDAO.lock_product(session, product_id)
        if product is None:
            raise ValueError("Product not found")
        mapping = await SupplierOfferMappingDAO.lock_mapping_for_offer(
            session,
            supplier_id=int(offer.supplier_id),
            external_id=offer.external_id,
        )
        SupplierOfferMappingService._validate_expected_state(
            mapping=mapping,
            expected_mapping_id=expected_mapping_id,
            expected_product_id=expected_product_id,
        )

        if mapping is not None and mapping.is_active:
            if mapping.product_id == product_id:
                await session.commit()
                return SupplierOfferMappingService._response(offer_id, mapping)
            if not replace_existing:
                raise SupplierOfferMappingConflictError(
                    "Supplier offer is already mapped: "
                    f"mapping_id={mapping.id}, product_id={mapping.product_id}; "
                    "reload candidates or set replace_existing with both expected ids"
                )

        now = datetime.now()
        if mapping is None:
            mapping = ProductSupplierMapping(
                product_id=product_id,
                supplier_id=int(offer.supplier_id),
                external_id=offer.external_id,
                is_active=True,
                mapped_by=mapped_by,
                mapped_at=now,
            )
        else:
            mapping.product_id = product_id
            mapping.is_active = True
            mapping.mapped_by = mapped_by
            mapping.mapped_at = now
        session.add(mapping)
        offer_supplier_id = int(offer.supplier_id)
        offer_external_id = offer.external_id
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            concurrent = await SupplierOfferMappingDAO.lock_mapping_for_offer(
                session,
                supplier_id=offer_supplier_id,
                external_id=offer_external_id,
            )
            if concurrent is not None:
                raise SupplierOfferMappingConflictError(
                    "Supplier offer mapping changed concurrently: "
                    f"mapping_id={concurrent.id}, product_id={concurrent.product_id}; reload candidates"
                ) from exc
            raise
        await session.refresh(mapping)
        return SupplierOfferMappingService._response(offer_id, mapping)

    @staticmethod
    def _response(offer_id: int, mapping: ProductSupplierMapping) -> dict:
        return {
            "offer_id": offer_id,
            "id": mapping.id,
            "product_id": mapping.product_id,
            "supplier_id": mapping.supplier_id,
            "external_id": mapping.external_id,
            "is_active": mapping.is_active,
            "mapped_by": mapping.mapped_by,
            "mapped_at": mapping.mapped_at,
        }
