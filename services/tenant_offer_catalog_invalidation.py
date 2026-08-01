from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from models.tenancy import TenantScope
from services.catalog_revision_service import CatalogRevisionService


class TenantOfferCatalogInvalidationUnavailableError(RuntimeError):
    """Raised when a routable lifecycle change cannot stage invalidation."""


class TenantOfferCatalogInvalidationAdapter:
    """Bridge offer mutations to the contextual revision/outbox release.

    The current foundation release does not expose ``stage_invalidation`` yet.
    Once the reviewed storefront-revision branch is rebased, the same adapter
    stages its revision and durable outbox event inside the caller transaction.
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
        await stage_invalidation(
            session,
            reason=reason,
            tenant_scope=tenant_scope,
            product_ids=tuple(sorted({int(value) for value in product_ids})),
            slugs=tuple(sorted({str(value) for value in slugs if str(value)})),
        )
        return True
