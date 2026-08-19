from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from crud.catalog_revision import CatalogRevisionDAO
from models.tenancy import TenantScope
from services.catalog_revision_service import CatalogRevisionService


class ProductCollectionInvalidationService:
    """Stage exact-storefront collection cache invalidation in the command transaction."""

    @staticmethod
    async def stage(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        reason: str,
    ) -> bool:
        targets = await CatalogRevisionDAO.list_invalidation_targets(
            session,
            tenant_scope=tenant_scope,
        )
        if not targets:
            # Draft/disabled storefronts have no public cache target yet.
            return False
        if len(targets) != 1:
            raise RuntimeError("Product collection invalidation target is ambiguous")
        await CatalogRevisionService.stage_invalidation(
            session,
            reason=reason,
            tenant_scope=tenant_scope,
            additional_paths=("/", "/catalog/"),
        )
        return True


__all__ = ["ProductCollectionInvalidationService"]
