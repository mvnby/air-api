from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.tenancy import Storefront, StorefrontDomain, Tenant, TenantMembership


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
    tenant_is_system: bool = False


@dataclass(frozen=True)
class TenantScopeRow:
    """Server-resolved IDs for a tenant's canonical storefront."""

    tenant_id: int
    storefront_id: int
    is_system: bool = True


@dataclass(frozen=True)
class ManagerTenantAccessRow:
    membership_id: int
    tenant_id: int
    storefront_id: int
    role: str
    is_system: bool


class TenancyDAO:
    @staticmethod
    async def get_active_storefront_for_tenant_slug(
        session: AsyncSession,
        *,
        tenant_id: int,
        storefront_slug: str,
    ) -> Storefront | None:
        result = await session.execute(
            select(Storefront).where(
                Storefront.tenant_id == tenant_id,
                Storefront.slug == storefront_slug,
                Storefront.status == "active",
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_active_storefronts_for_tenant(
        session: AsyncSession,
        *,
        tenant_id: int,
    ) -> list[Storefront]:
        result = await session.execute(
            select(Storefront)
            .where(
                Storefront.tenant_id == tenant_id,
                Storefront.status == "active",
            )
            .order_by(
                Storefront.is_default.desc(),
                Storefront.display_name.asc(),
                Storefront.id.asc(),
            )
        )
        return list(result.scalars().all())

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
                is_system=bool(tenant.is_system),
            )
            for tenant, storefront in rows
        ]

    @staticmethod
    async def list_active_manager_access_candidates(
        session: AsyncSession,
        *,
        staff_user_id: int,
    ) -> list[ManagerTenantAccessRow]:
        """Return all active memberships with an active default storefront.

        Selection of one membership is deliberately left to the service layer.
        Until the Manager UI has an explicit tenant switcher, more than one
        candidate is ambiguous and must fail closed.
        """
        statement = (
            select(TenantMembership, Tenant, Storefront)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .join(Storefront, Storefront.tenant_id == Tenant.id)
            .where(
                TenantMembership.staff_user_id == staff_user_id,
                TenantMembership.status == "active",
                Tenant.status == "active",
                Storefront.status == "active",
                Storefront.is_default.is_(True),
            )
            .order_by(TenantMembership.id.asc(), Storefront.id.asc())
        )
        rows = (await session.execute(statement)).all()
        return [
            ManagerTenantAccessRow(
                membership_id=int(membership.id or 0),
                tenant_id=int(tenant.id or 0),
                storefront_id=int(storefront.id or 0),
                role=str(membership.role or "").strip().lower(),
                is_system=bool(tenant.is_system),
            )
            for membership, tenant, storefront in rows
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
            tenant_is_system=bool(tenant.is_system),
        )

    @staticmethod
    async def get_active_storefront_by_scope(
        session: AsyncSession,
        *,
        tenant_id: int,
        storefront_id: int,
    ) -> StorefrontContextRow | None:
        statement = (
            select(Tenant, Storefront, StorefrontDomain)
            .join(Storefront, Storefront.tenant_id == Tenant.id)
            .join(StorefrontDomain, StorefrontDomain.storefront_id == Storefront.id)
            .where(
                Tenant.id == tenant_id,
                Tenant.status == "active",
                Storefront.id == storefront_id,
                Storefront.status == "active",
                StorefrontDomain.status == "active",
                StorefrontDomain.is_primary.is_(True),
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
            tenant_is_system=bool(tenant.is_system),
        )
