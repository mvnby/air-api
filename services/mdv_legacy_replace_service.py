from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Brand, OrderProductLink, Product
from services.catalog_revision_service import CatalogRevisionService
from services.product_manager_service import ProductManagerService


REPLACEABLE_MDV_CATALOGS = {"semi", "multi"}


class MdvLegacyReplaceService:
    @staticmethod
    def normalize_catalogs(catalogs: list[str] | None) -> list[str]:
        result: list[str] = []
        for catalog in catalogs or []:
            value = str(catalog or "").strip()
            if value in REPLACEABLE_MDV_CATALOGS and value not in result:
                result.append(value)
        return result

    @staticmethod
    async def preview(
        session: AsyncSession,
        *,
        catalogs: list[str] | None,
        sample_limit: int = 20,
    ) -> dict[str, Any]:
        selected = MdvLegacyReplaceService.normalize_catalogs(catalogs)
        if not selected:
            return MdvLegacyReplaceService._empty_report()

        candidates = await MdvLegacyReplaceService._find_candidates(session, selected)
        linked_ids = await MdvLegacyReplaceService._order_linked_ids(
            session,
            [product.id for product, _catalog in candidates if product.id],
        )

        by_catalog: Counter[str] = Counter(catalog for _product, catalog in candidates)
        deletable = 0
        keep_for_update = 0
        samples: list[dict[str, Any]] = []
        for product, catalog in candidates:
            if not product.id:
                continue
            action = "keep_for_update" if product.id in linked_ids else "delete"
            if action == "delete":
                deletable += 1
            else:
                keep_for_update += 1
            if len(samples) < sample_limit:
                samples.append(MdvLegacyReplaceService._sample(product, catalog, action))

        return {
            "enabled": True,
            "catalogs": selected,
            "total": len(candidates),
            "by_catalog": dict(by_catalog),
            "deletable_count": deletable,
            "keep_for_update_count": keep_for_update,
            "deleted_count": 0,
            "archived_count": 0,
            "samples": samples,
        }

    @staticmethod
    async def execute(
        session: AsyncSession,
        *,
        catalogs: list[str] | None,
    ) -> dict[str, Any]:
        selected = MdvLegacyReplaceService.normalize_catalogs(catalogs)
        if not selected:
            return MdvLegacyReplaceService._empty_report()

        candidates = await MdvLegacyReplaceService._find_candidates(session, selected)
        linked_ids = await MdvLegacyReplaceService._order_linked_ids(
            session,
            [product.id for product, _catalog in candidates if product.id],
        )

        deleted = 0
        archived = 0
        deleted_ids: list[int] = []
        deleted_slugs: list[str] = []
        deleted_brand_slugs: list[str] = []
        archived_ids: list[int] = []
        samples: list[dict[str, Any]] = []
        by_catalog: Counter[str] = Counter()

        for product, catalog in candidates:
            if not product.id:
                continue
            by_catalog[catalog] += 1
            if product.id in linked_ids:
                product.is_published = False
                product.specs = {
                    **(product.specs or {}),
                    "__mdv_legacy_replace_pending": True,
                    "__mdv_legacy_replace_catalog": catalog,
                }
                session.add(product)
                archived += 1
                archived_ids.append(product.id)
                action = "keep_for_update"
            else:
                deletion = await ProductManagerService.stage_delete_for_manager(
                    session,
                    product.id,
                )
                if deletion is None:
                    continue
                deleted += 1
                deleted_ids.append(deletion.product_id)
                if deletion.slug:
                    deleted_slugs.append(deletion.slug)
                deleted_brand_slugs.extend(deletion.brand_slugs)
                action = "delete"

            if len(samples) < 20:
                samples.append(MdvLegacyReplaceService._sample(product, catalog, action))

        affected_ids = [*deleted_ids, *archived_ids]
        if affected_ids:
            await CatalogRevisionService.stage_invalidation(
                session,
                reason="mdv_legacy_replace",
                product_ids=affected_ids,
                slugs=deleted_slugs,
                brand_slugs=deleted_brand_slugs,
            )
            await session.commit()

        return {
            "enabled": True,
            "catalogs": selected,
            "total": len(candidates),
            "by_catalog": dict(by_catalog),
            "deletable_count": deleted,
            "keep_for_update_count": archived,
            "deleted_count": deleted,
            "archived_count": archived,
            "samples": samples,
        }

    @staticmethod
    async def _find_candidates(
        session: AsyncSession,
        catalogs: list[str],
    ) -> list[tuple[Product, str]]:
        rows = (
            await session.execute(
                select(Product)
                .outerjoin(Brand, Product.brand_id == Brand.id)
                .where(
                    or_(
                        Brand.slug == "mdv",
                        Product.title.ilike("%MDV%"),
                        Product.source_url.ilike("%mdv-aircond.ru%"),
                    )
                )
                .options(selectinload(Product.tags), selectinload(Product.brand))
                .order_by(Product.id)
            )
        ).scalars().all()

        result: list[tuple[Product, str]] = []
        for product in rows:
            catalog = MdvLegacyReplaceService._catalog_for_product(product)
            if catalog in catalogs:
                result.append((product, catalog))
        return result

    @staticmethod
    async def _order_linked_ids(
        session: AsyncSession,
        product_ids: list[int],
    ) -> set[int]:
        if not product_ids:
            return set()
        rows = (
            await session.execute(
                select(OrderProductLink.product_id)
                .where(OrderProductLink.product_id.in_(product_ids))
            )
        ).scalars().all()
        return {int(product_id) for product_id in rows if product_id is not None}

    @staticmethod
    def _catalog_for_product(product: Product) -> str | None:
        specs = product.specs if isinstance(product.specs, dict) else {}
        explicit = str(
            specs.get("__mdv_catalog")
            or specs.get("mdv_catalog")
            or ""
        ).strip()
        if explicit in REPLACEABLE_MDV_CATALOGS:
            return explicit

        source_url = str(product.source_url or "").lower()
        if "/multisplit-sistemy/" in source_url:
            return "multi"
        if "/polupromyshlennye-split-sistemy/" in source_url:
            return "semi"

        tag_slugs = {str(getattr(tag, "slug", "") or "") for tag in product.tags or []}
        type_text = str(specs.get("type") or "").lower()
        title = str(product.title or "").lower()

        if "cat-multi" in tag_slugs or "мульти" in type_text or "мульти" in title:
            return "multi"
        if "cat-industrial" in tag_slugs or "полупром" in type_text or "полупром" in title:
            return "semi"
        return None

    @staticmethod
    def _sample(product: Product, catalog: str, action: str) -> dict[str, Any]:
        return {
            "product_id": product.id,
            "title": product.title,
            "slug": product.slug,
            "catalog": catalog,
            "action": action,
            "is_published": product.is_published,
            "source_url": product.source_url or "",
        }

    @staticmethod
    def _empty_report() -> dict[str, Any]:
        return {
            "enabled": False,
            "catalogs": [],
            "total": 0,
            "by_catalog": {},
            "deletable_count": 0,
            "keep_for_update_count": 0,
            "deleted_count": 0,
            "archived_count": 0,
            "samples": [],
        }
