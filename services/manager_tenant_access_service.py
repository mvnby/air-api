from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from crud.tenancy import TenancyDAO
from models.tenancy import TenantScope


class ManagerTenantAccessResolutionError(RuntimeError):
    """Raised when a staff identity has no unambiguous active tenant access."""


@dataclass(frozen=True)
class ManagerTenantAccess:
    membership_id: int
    role: str
    tenant_scope: TenantScope


class ManagerTenantAccessResolver:
    @staticmethod
    async def resolve(
        session: AsyncSession,
        *,
        staff_user_id: int,
    ) -> ManagerTenantAccess:
        candidates = await TenancyDAO.list_active_manager_access_candidates(
            session,
            staff_user_id=staff_user_id,
        )
        if len(candidates) != 1:
            raise ManagerTenantAccessResolutionError(
                "Active tenant membership is missing or ambiguous"
            )

        candidate = candidates[0]
        if (
            candidate.membership_id <= 0
            or candidate.tenant_id <= 0
            or candidate.storefront_id <= 0
            or not candidate.role
        ):
            raise ManagerTenantAccessResolutionError(
                "Active tenant membership is invalid"
            )
        return ManagerTenantAccess(
            membership_id=candidate.membership_id,
            role=candidate.role,
            tenant_scope=TenantScope(
                tenant_id=candidate.tenant_id,
                storefront_id=candidate.storefront_id,
                is_system=candidate.is_system,
            ),
        )
