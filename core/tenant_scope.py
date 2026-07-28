"""Trusted tenant-scope dependencies for the single-tenant rollout stage."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from services.tenant_scope_service import SystemTenantScopeResolver, TenantScope


async def get_system_tenant_scope(
    session: AsyncSession = Depends(get_session),
) -> TenantScope:
    """Resolve the canonical MVN scope without accepting client-owned input."""
    return await SystemTenantScopeResolver.resolve(session)
