from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from crud.tenancy import TenancyDAO
from models.tenancy import TenantScope


MANAGER_STOREFRONT_HEADER = "X-MVN-Manager-Storefront"
STOREFRONT_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class ManagerStorefrontSelectionError(RuntimeError):
    """Raised when a requested storefront is invalid or outside the tenant."""


class ManagerStorefrontSelector:
    @staticmethod
    async def resolve(
        session: AsyncSession,
        *,
        base_scope: TenantScope,
        requested_slug: str | None,
    ) -> TenantScope:
        if requested_slug is None:
            return base_scope

        normalized_slug = str(requested_slug).strip().lower()
        if not STOREFRONT_SLUG_PATTERN.fullmatch(normalized_slug):
            raise ManagerStorefrontSelectionError("Storefront access denied")

        storefront = await TenancyDAO.get_active_storefront_for_tenant_slug(
            session,
            tenant_id=base_scope.tenant_id,
            storefront_slug=normalized_slug,
        )
        if storefront is None or not storefront.id:
            raise ManagerStorefrontSelectionError("Storefront access denied")

        return TenantScope(
            tenant_id=base_scope.tenant_id,
            storefront_id=int(storefront.id),
            is_system=base_scope.is_system,
        )

    @staticmethod
    async def list_available(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> dict:
        storefronts = await TenancyDAO.list_active_storefronts_for_tenant(
            session,
            tenant_id=tenant_scope.tenant_id,
        )
        return {
            "items": [
                {
                    "slug": storefront.slug,
                    "display_name": storefront.display_name,
                    "city": storefront.city,
                    "default_locale": storefront.default_locale,
                    "currency": storefront.currency,
                    "is_default": storefront.is_default,
                    "is_current": storefront.id == tenant_scope.storefront_id,
                }
                for storefront in storefronts
            ]
        }
