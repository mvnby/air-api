"""Catalog reference inheritance and the atomic Manager editing boundary."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Brand, Product, ProductSeries
from models.catalog_document import CatalogDocument
from schemas_catalog_documents import (
    CatalogDocumentInput,
    CatalogDocumentResponse,
    CatalogDocumentsReplacePayload,
    CatalogDocumentTarget,
    CatalogDocumentWorkspace,
)
from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService


_TARGET_MODELS = {"brand": Brand, "series": ProductSeries, "product": Product}
_INPUT_FIELDS = tuple(CatalogDocumentInput.model_fields)


class CatalogDocumentService:
    @staticmethod
    async def require_target(
        session: AsyncSession,
        *,
        target_type: CatalogDocumentTarget,
        target_id: int,
        lock: bool = False,
    ) -> Any:
        model = _TARGET_MODELS.get(target_type)
        if model is None:
            raise HTTPException(status_code=400, detail="Неизвестный тип владельца документа.")
        if lock:
            target = (await session.execute(select(model).where(model.id == target_id).with_for_update())).scalar_one_or_none()
        else:
            target = await session.get(model, target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Бренд, серия или товар не найдены.")
        return target

    @staticmethod
    async def _chain(session: AsyncSession, target_type: CatalogDocumentTarget, target: Any):
        """Most specific first; inconsistent brand/series links never leak sources."""
        chain = [(target_type, target)]
        brand_id = None
        if target_type == "product":
            brand_id = target.brand_id
            if target.series_id:
                series = await session.get(ProductSeries, target.series_id)
                if series is not None and (brand_id is None or series.brand_id == brand_id):
                    chain.append(("series", series))
                    brand_id = brand_id or series.brand_id
        elif target_type == "series":
            brand_id = target.brand_id
        if brand_id:
            brand = await session.get(Brand, brand_id)
            if brand is not None:
                chain.append(("brand", brand))
        return chain

    @staticmethod
    def _serialize(document: CatalogDocument, *, origin_type: CatalogDocumentTarget, origin: Any, inherited: bool, public_only: bool = False):
        payload = {name: getattr(document, name) for name in _INPUT_FIELDS}
        # Supplier research provenance is for staff; the material link itself is public.
        if public_only:
            payload["source_url"] = None
        return CatalogDocumentResponse(
            **payload,
            id=int(document.id),
            origin_type=origin_type,
            origin_id=int(origin.id),
            origin_title=origin.title,
            inherited=inherited,
        )

    @staticmethod
    def _deduplicate(items: list[CatalogDocumentResponse]) -> list[CatalogDocumentResponse]:
        result = []
        seen = set()
        for item in items:
            if item.url not in seen:
                seen.add(item.url)
                result.append(item)
        return result

    @classmethod
    async def get_workspace(
        cls,
        session: AsyncSession,
        *,
        target_type: CatalogDocumentTarget,
        target_id: int,
        public_only: bool = False,
    ) -> CatalogDocumentWorkspace:
        target = await cls.require_target(session, target_type=target_type, target_id=target_id)
        if public_only and not target.is_published:
            return CatalogDocumentWorkspace()
        own: list[CatalogDocumentResponse] = []
        inherited: list[CatalogDocumentResponse] = []
        public_seen: set[str] = set()
        for index, (origin_type, origin) in enumerate(await cls._chain(session, target_type, target)):
            if public_only and not origin.is_published:
                continue
            statement = select(CatalogDocument).where(getattr(CatalogDocument, f"{origin_type}_id") == origin.id)
            if index:
                statement = statement.where(CatalogDocument.inherit_to_products.is_(True))
            documents = (await session.execute(statement.order_by(CatalogDocument.sort_order, CatalogDocument.id))).scalars().all()
            destination = inherited if index else own
            for document in documents:
                if public_only:
                    # More-specific private metadata also suppresses an ancestor's
                    # duplicate reference; publication must not resurrect it.
                    if document.url in public_seen:
                        continue
                    public_seen.add(document.url)
                    if document.visibility != "public":
                        continue
                destination.append(cls._serialize(document, origin_type=origin_type, origin=origin, inherited=bool(index), public_only=public_only))
        return CatalogDocumentWorkspace(own=own, inherited=inherited, effective=cls._deduplicate(own + inherited))

    @classmethod
    async def get_effective_documents(
        cls,
        session: AsyncSession,
        *,
        target_type: CatalogDocumentTarget,
        target_id: int,
        public_only: bool = True,
    ) -> list[CatalogDocumentResponse]:
        return (await cls.get_workspace(session, target_type=target_type, target_id=target_id, public_only=public_only)).effective

    @classmethod
    async def resolve_for_products(
        cls,
        session: AsyncSession,
        products: Iterable[Product],
        *,
        public_only: bool = True,
    ) -> dict[int, list[CatalogDocumentResponse]]:
        """Resolve a product page/list in at most three bounded queries."""
        products = [product for product in products if product.id is not None]
        if not products:
            return {}
        series_ids = {product.series_id for product in products if product.series_id}
        series = {
            item.id: item for item in (
                await session.execute(select(ProductSeries).where(ProductSeries.id.in_(series_ids)))
            ).scalars().all()
        } if series_ids else {}
        brand_ids = {product.brand_id for product in products if product.brand_id}
        brand_ids.update(item.brand_id for item in series.values() if item.brand_id)
        brands = {
            item.id: item for item in (
                await session.execute(select(Brand).where(Brand.id.in_(brand_ids)))
            ).scalars().all()
        } if brand_ids else {}
        statement = select(CatalogDocument).where(or_(
            CatalogDocument.product_id.in_([product.id for product in products]),
            CatalogDocument.series_id.in_(series_ids),
            CatalogDocument.brand_id.in_(brand_ids),
        )).order_by(CatalogDocument.sort_order, CatalogDocument.id)
        documents_by_owner: dict[tuple[str, int], list[CatalogDocument]] = {}
        for document in (await session.execute(statement)).scalars().all():
            for kind in _TARGET_MODELS:
                owner_id = getattr(document, f"{kind}_id")
                if owner_id is not None:
                    documents_by_owner.setdefault((kind, owner_id), []).append(document)
                    break
        if public_only:
            # These share SQLAlchemy's identity map with eager-loaded product.series.
            for product_series in series.values():
                series_documents = []
                seen: set[str] = set()
                if product_series.is_published:
                    origins = [("series", product_series)]
                    if product_series.brand_id in brands:
                        origins.append(("brand", brands[product_series.brand_id]))
                    for index, (kind, origin) in enumerate(origins):
                        if not origin.is_published:
                            continue
                        for document in documents_by_owner.get((kind, origin.id), []):
                            if index and not document.inherit_to_products or document.url in seen:
                                continue
                            seen.add(document.url)
                            if document.visibility == "public":
                                series_documents.append(cls._serialize(document, origin_type=kind, origin=origin, inherited=bool(index), public_only=True))
                product_series.__dict__["_catalog_documents"] = cls._deduplicate(series_documents)
        result = {}
        for product in products:
            chain = [("product", product)]
            brand_id = product.brand_id
            product_series = series.get(product.series_id)
            if product_series is not None and (brand_id is None or product_series.brand_id == brand_id):
                chain.append(("series", product_series))
                brand_id = brand_id or product_series.brand_id
            if brand_id in brands:
                chain.append(("brand", brands[brand_id]))
            resolved = []
            seen: set[str] = set()
            if not public_only or product.is_published:
                for index, (kind, origin) in enumerate(chain):
                    if public_only and not origin.is_published:
                        continue
                    for document in documents_by_owner.get((kind, origin.id), []):
                        if index and not document.inherit_to_products or document.url in seen:
                            continue
                        seen.add(document.url)
                        if not public_only or document.visibility == "public":
                            resolved.append(cls._serialize(document, origin_type=kind, origin=origin, inherited=bool(index), public_only=public_only))
            result[int(product.id)] = cls._deduplicate(resolved)
        return result

    @classmethod
    async def replace_documents(
        cls,
        session: AsyncSession,
        *,
        target_type: CatalogDocumentTarget,
        target_id: int,
        payload: CatalogDocumentsReplacePayload,
    ) -> CatalogDocumentWorkspace:
        target = await cls.require_target(session, target_type=target_type, target_id=target_id, lock=True)
        urls = [item.url for item in payload.documents]
        if len(urls) != len(set(urls)):
            raise HTTPException(status_code=400, detail="Один документ нельзя добавить дважды по одинаковой ссылке.")
        existing = (await session.execute(
            select(CatalogDocument)
            .where(getattr(CatalogDocument, f"{target_type}_id") == target_id)
            .order_by(CatalogDocument.sort_order, CatalogDocument.id)
        )).scalars().all()
        before = [{name: getattr(item, name) for name in _INPUT_FIELDS} for item in existing]
        requested = [item.model_dump() for item in payload.documents]
        changed = before != requested
        if changed:
            by_url = {item.url: item for item in existing}
            for document in existing:
                if document.url not in urls:
                    await session.delete(document)
            for position, fields in enumerate(requested):
                document = by_url.get(fields["url"])
                if document is None:
                    document = CatalogDocument(**{f"{target_type}_id": target_id}, **fields, sort_order=position)
                else:
                    for name, value in fields.items():
                        setattr(document, name, value)
                    document.sort_order = position
                session.add(document)
            await session.flush()
        chain = await cls._chain(session, target_type, target)
        brand_slugs = [origin.slug for kind, origin in chain if kind == "brand"]
        await CatalogInvalidationCommitService.commit_registered_global_mutation(
            session,
            producer="catalog_documents.replace_documents",
            changed=changed,
            product_ids=[target_id] if target_type == "product" else None,
            slugs=[target.slug] if target_type == "product" else None,
            brand_slugs=brand_slugs,
        )
        return await cls.get_workspace(session, target_type=target_type, target_id=target_id)
