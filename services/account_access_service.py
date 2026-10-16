"""Actual account and installer membership access, separate from Manager rights."""

from crud.tenancy import TenancyDAO
from models.tenancy import TenantScope
from services.manager_tenant_access_service import (
    ManagerTenantAccess, ManagerTenantAccessResolutionError, ManagerTenantAccessResolver, WORKSPACE_ROLES,
)


class AccountAccessResolver(ManagerTenantAccessResolver):
    """Personal login/profile eligibility; never creates a virtual membership."""

    ROLES = WORKSPACE_ROLES | {"installer"}

    @classmethod
    async def candidates(cls, session, *, staff_user_id):
        rows = await TenancyDAO.list_active_manager_access_candidates(session, staff_user_id=staff_user_id)
        return [row for row in rows if row.role in cls.ROLES]

    @classmethod
    def _access(cls, candidate):
        if (candidate.membership_id <= 0 or candidate.tenant_id <= 0
                or candidate.storefront_id <= 0 or candidate.role not in cls.ROLES):
            raise ManagerTenantAccessResolutionError("Active account membership is invalid")
        return ManagerTenantAccess(
            membership_id=candidate.membership_id, role=candidate.role, permissions=candidate.permissions,
            tenant_scope=TenantScope(tenant_id=candidate.tenant_id, storefront_id=candidate.storefront_id,
                                    is_system=candidate.is_system, demo_read_only=candidate.demo_read_only),
        )


class InstallerTenantAccessResolver(AccountAccessResolver):
    """A real selected membership; assignment access remains a separate check."""

    ROLES = frozenset({"owner", "admin", "manager", "installer"})
