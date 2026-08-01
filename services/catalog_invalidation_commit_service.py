"""Atomic commit boundary for global catalog mutations and invalidations."""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from services.catalog_revision_service import CatalogRevisionService


class CatalogInvalidationCommitService:
    @staticmethod
    async def commit_global_mutation(
        session: AsyncSession,
        *,
        reason: str,
        product_ids: Iterable[int] | None = None,
        slugs: Iterable[str] | None = None,
        brand_slugs: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Commit business changes and their revision/outbox event together."""

        revision = await CatalogRevisionService.stage_invalidation(
            session,
            reason=reason,
            product_ids=product_ids,
            slugs=slugs,
            brand_slugs=brand_slugs,
        )
        await session.commit()
        return revision
