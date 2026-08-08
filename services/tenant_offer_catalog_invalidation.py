from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from crud.catalog_revision import CatalogRevisionDAO
from models.tenancy import TenantScope
from services.catalog_revision_service import CatalogRevisionService


class TenantOfferCatalogInvalidationUnavailableError(RuntimeError):
    """Raised when a routable lifecycle change cannot stage invalidation."""


class TenantOfferCatalogInvalidationAdapter:
    """Bridge offer mutations to the contextual revision/outbox release.

    Draft storefronts have no public cache target yet, so ordinary offer
    staging may safely defer invalidation until activation. Routable lifecycle
    changes set ``required=True`` and fail closed if the exact target is absent.
    """

    @staticmethod
    def available() -> bool:
        return callable(
            getattr(CatalogRevisionService, "stage_invalidation", None)
        )

    @staticmethod
    async def stage(
        session: AsyncSession,
        *,
        reason: str,
        tenant_scope: TenantScope,
        product_ids: Iterable[int],
        slugs: Iterable[str],
        required: bool = False,
    ) -> bool:
        stage_invalidation = getattr(
            CatalogRevisionService,
            "stage_invalidation",
            None,
        )
        if not callable(stage_invalidation):
            if required:
                raise TenantOfferCatalogInvalidationUnavailableError(
                    "Storefront catalog invalidation staging is unavailable"
                )
            return False
        targets = await CatalogRevisionDAO.list_invalidation_targets(
            session,
            tenant_scope=tenant_scope,
        )
        if not targets:
            if required:
                raise TenantOfferCatalogInvalidationUnavailableError(
                    "Storefront catalog invalidation target is not routable"
                )
            return False
        if len(targets) != 1:
            raise TenantOfferCatalogInvalidationUnavailableError(
                "Storefront catalog invalidation target is ambiguous"
            )
        await stage_invalidation(
            session,
            reason=reason,
            tenant_scope=tenant_scope,
            product_ids=tuple(sorted({int(value) for value in product_ids})),
            slugs=tuple(sorted({str(value) for value in slugs if str(value)})),
        )
        return True
