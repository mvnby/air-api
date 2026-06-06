from typing import Any, Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from crud.catalog_revision import CatalogRevisionDAO, CatalogRevisionSnapshot


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
