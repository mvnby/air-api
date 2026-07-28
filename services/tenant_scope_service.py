from __future__ import annotations

from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from crud.tenancy import TenancyDAO
from models.tenancy import TenantScope


class TenantScopeResolutionError(RuntimeError):
    """Raised when the canonical server-owned tenant scope is not unique."""


def tenant_or_fully_legacy_scope_clause(
    entity: Any,
    tenant_scope: TenantScope,
):
    """Match the current tenant or a genuinely pre-scope row.

    A row with only one provenance field populated is not legacy and must not
    be claimed by another request during the expand/backfill rollout.
    """
    return or_(
        entity.tenant_id == tenant_scope.tenant_id,
        and_(
            entity.tenant_id.is_(None),
            entity.storefront_id.is_(None),
        ),
    )


def storefront_or_fully_legacy_scope_clause(
    entity: Any,
    tenant_scope: TenantScope,
):
    """Match the exact storefront pair or a genuinely pre-scope row."""
    return or_(
        and_(
            entity.tenant_id == tenant_scope.tenant_id,
            entity.storefront_id == tenant_scope.storefront_id,
        ),
        and_(
            entity.tenant_id.is_(None),
            entity.storefront_id.is_(None),
        ),
    )


class SystemTenantScopeResolver:
    @staticmethod
    async def resolve(
        session: AsyncSession,
        *,
        tenant_slug: str = "mvn",
        storefront_slug: str = "main",
    ) -> TenantScope:
        """Resolve the one canonical MVN scope without accepting client input."""
        candidates = await TenancyDAO.list_active_system_scope_candidates(
            session,
            tenant_slug=tenant_slug,
            storefront_slug=storefront_slug,
        )
        if len(candidates) != 1:
            raise TenantScopeResolutionError("Canonical system tenant scope is unavailable")

        candidate = candidates[0]
        if candidate.tenant_id <= 0 or candidate.storefront_id <= 0:
            raise TenantScopeResolutionError("Canonical system tenant scope is invalid")
        return TenantScope(
            tenant_id=candidate.tenant_id,
            storefront_id=candidate.storefront_id,
        )
