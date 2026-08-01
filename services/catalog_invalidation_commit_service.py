"""Atomic commit boundary for global catalog mutations and invalidations."""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from services.catalog_mutation_contracts import (
    require_global_catalog_mutation_contract,
)
from services.catalog_revision_service import CatalogRevisionService


class CatalogInvalidationCommitService:
    @staticmethod
    async def commit_registered_global_mutation(
        session: AsyncSession,
        *,
        producer: str,
        changed: bool,
        product_ids: Iterable[int] | None = None,
        slugs: Iterable[str] | None = None,
        brand_slugs: Iterable[str] | None = None,
    ) -> dict[str, Any] | None:
        """Commit one registered producer, invalidating only real mutations."""

        contract = require_global_catalog_mutation_contract(producer)
        if not changed:
            await session.commit()
            return None
        return await CatalogInvalidationCommitService.commit_global_mutation(
            session,
            reason=contract.reason,
            product_ids=product_ids,
            slugs=slugs,
            brand_slugs=brand_slugs,
        )

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
