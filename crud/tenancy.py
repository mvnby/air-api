from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.tenancy import Storefront, StorefrontDomain, Tenant


@dataclass(frozen=True)
class StorefrontContextRow:
    tenant_id: int
    tenant_slug: str
    tenant_kind: str
    storefront_id: int
    storefront_slug: str
    storefront_name: str
    hostname: str
    city: str | None
    default_locale: str
    currency: str


@dataclass(frozen=True)
class TenantScopeRow:
    """Server-resolved IDs for a tenant's canonical storefront."""

    tenant_id: int
    storefront_id: int


class TenancyDAO:
    @staticmethod
    async def list_active_system_scope_candidates(
        session: AsyncSession,
        *,
        tenant_slug: str,
        storefront_slug: str,
    ) -> list[TenantScopeRow]:
        """Return every matching system/default storefront pair.

        The caller deliberately receives all matches so it can fail closed if
        data that should be unique is missing or ambiguous.
        """
        statement = (
            select(Tenant, Storefront)
            .join(Storefront, Storefront.tenant_id == Tenant.id)
            .where(
                Tenant.slug == tenant_slug,
                Tenant.is_system.is_(True),
                Tenant.status == "active",
                Storefront.slug == storefront_slug,
                Storefront.status == "active",
                Storefront.is_default.is_(True),
            )
        )
        rows = (await session.execute(statement)).all()
        return [
            TenantScopeRow(
                tenant_id=int(tenant.id or 0),
                storefront_id=int(storefront.id or 0),
            )
            for tenant, storefront in rows
        ]

    @staticmethod
    async def get_active_storefront_by_hostname(
        session: AsyncSession,
        hostname: str,
    ) -> StorefrontContextRow | None:
        statement = (
            select(Tenant, Storefront, StorefrontDomain)
            .join(Storefront, Storefront.tenant_id == Tenant.id)
            .join(StorefrontDomain, StorefrontDomain.storefront_id == Storefront.id)
            .where(
                Tenant.status == "active",
                Storefront.status == "active",
                StorefrontDomain.status == "active",
                StorefrontDomain.hostname == hostname,
            )
        )
        row = (await session.execute(statement)).first()
        if row is None:
            return None

        tenant, storefront, domain = row
        return StorefrontContextRow(
            tenant_id=int(tenant.id),
            tenant_slug=tenant.slug,
            tenant_kind=tenant.kind,
            storefront_id=int(storefront.id),
            storefront_slug=storefront.slug,
            storefront_name=storefront.display_name,
            hostname=domain.hostname,
            city=storefront.city,
            default_locale=storefront.default_locale,
            currency=storefront.currency,
        )
