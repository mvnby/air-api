import logging
from typing import Any, Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.catalog_revision import CatalogRevisionDAO, CatalogRevisionSnapshot
from models import Brand, Product
from services.catalog_purge_service import cloudflare_catalog_purge_service


logger = logging.getLogger(__name__)


class CatalogRevisionService:
    @staticmethod
    def _serialize(row: CatalogRevisionSnapshot) -> dict[str, Any]:
        return {
            "revision": row.revision,
            "updated_at": row.updated_at,
        }

    @staticmethod
    async def get_current(session: AsyncSession) -> dict[str, Any]:
        row = await CatalogRevisionDAO.get_current(session)
        return CatalogRevisionService._serialize(row)

    @staticmethod
    async def bump(
        session: AsyncSession,
        scope: str,
        product_ids: Optional[Iterable[int]] = None,
        slugs: Optional[Iterable[str]] = None,
        brand_slugs: Optional[Iterable[str]] = None,
    ) -> dict[str, Any]:
        row = await CatalogRevisionDAO.bump(
            session,
            scope=scope,
            product_ids=product_ids,
            slugs=slugs,
            brand_slugs=brand_slugs,
        )
        return CatalogRevisionService._serialize(row)

    @staticmethod
    async def bump_commit_and_purge(
        session: AsyncSession,
        scope: str,
        product_ids: Optional[Iterable[int]] = None,
        slugs: Optional[Iterable[str]] = None,
        brand_slugs: Optional[Iterable[str]] = None,
    ) -> dict[str, Any]:
        product_id_values = CatalogRevisionService._normalize_ints(product_ids)
        product_slug_values = CatalogRevisionService._normalize_strings(slugs)
        explicit_brand_slug_values = CatalogRevisionService._normalize_strings(brand_slugs)

        (
            resolved_product_slug_values,
            resolved_brand_slug_values,
        ) = await CatalogRevisionService.get_product_purge_targets(session, product_id_values)
        purge_product_slugs = CatalogRevisionService._dedupe_strings(
            [*product_slug_values, *resolved_product_slug_values]
        )
        purge_brand_slugs = CatalogRevisionService._dedupe_strings(
            [*explicit_brand_slug_values, *resolved_brand_slug_values]
        )

        revision = await CatalogRevisionService.bump(
            session,
            scope=scope,
            product_ids=product_id_values,
            slugs=purge_product_slugs,
            brand_slugs=purge_brand_slugs,
        )
        await session.commit()

        try:
            await cloudflare_catalog_purge_service.purge_after_revision(
                scope=scope,
                revision=int(revision["revision"]),
                product_slugs=purge_product_slugs,
                brand_slugs=purge_brand_slugs,
            )
        except Exception as exc:
            logger.warning(
                "Catalog purge failed after committed revision scope=%s revision=%s error=%s",
                scope,
                revision["revision"],
                exc,
            )

        return revision

    @staticmethod
    async def get_product_purge_targets(
        session: AsyncSession,
        product_ids: Optional[Iterable[int]],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        product_id_values = CatalogRevisionService._normalize_ints(product_ids)
        if not product_id_values:
            return (), ()

        rows = (
            await session.execute(
                select(Product.slug, Brand.slug)
                .outerjoin(Brand, Product.brand_id == Brand.id)
                .where(Product.id.in_(product_id_values))
            )
        ).all()

        product_slugs = CatalogRevisionService._normalize_strings(row[0] for row in rows)
        brand_slugs = CatalogRevisionService._normalize_strings(row[1] for row in rows)
        return product_slugs, brand_slugs

    @staticmethod
    async def get_product_brand_slugs(
        session: AsyncSession,
        product_ids: Optional[Iterable[int]],
    ) -> tuple[str, ...]:
        _, brand_slugs = await CatalogRevisionService.get_product_purge_targets(session, product_ids)
        return brand_slugs

    @staticmethod
    def _normalize_ints(values: Optional[Iterable[int]]) -> tuple[int, ...]:
        result: list[int] = []
        for value in values or []:
            try:
                normalized = int(value)
            except (TypeError, ValueError):
                continue
            result.append(normalized)
        return tuple(dict.fromkeys(result))

    @staticmethod
    def _normalize_strings(values: Optional[Iterable[str]]) -> tuple[str, ...]:
        result: list[str] = []
        for value in values or []:
            normalized = str(value or "").strip()
            if normalized:
                result.append(normalized)
        return CatalogRevisionService._dedupe_strings(result)

    @staticmethod
    def _dedupe_strings(values: Iterable[str]) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return tuple(result)
