from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from crud.tenancy import TenancyDAO
from models.tenancy import TenantScope

WORKSPACE_ROLES = frozenset({"owner", "admin", "manager", "catalog_editor"})


class ManagerTenantAccessResolutionError(RuntimeError):
    def __init__(self, message: str, *, code: str = "company_access_denied"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ManagerTenantAccess:
    membership_id: int | None
    role: str
    tenant_scope: TenantScope
    permissions: tuple[str, ...] = ()
    access_kind: str = "membership"


class ManagerTenantAccessResolver:
    @staticmethod
    def _access(candidate):
        if (candidate.membership_id <= 0 or candidate.tenant_id <= 0
                or candidate.storefront_id <= 0 or candidate.role not in WORKSPACE_ROLES):
            raise ManagerTenantAccessResolutionError("Active tenant membership is invalid")
        return ManagerTenantAccess(
            membership_id=candidate.membership_id, role=candidate.role, permissions=candidate.permissions,
            tenant_scope=TenantScope(tenant_id=candidate.tenant_id, storefront_id=candidate.storefront_id,
                                    is_system=candidate.is_system, demo_read_only=candidate.demo_read_only),
        )

    @classmethod
    async def candidates(cls, session, *, staff_user_id):
        rows = await TenancyDAO.list_active_manager_access_candidates(session, staff_user_id=staff_user_id)
        return [row for row in rows if row.role in WORKSPACE_ROLES]

    @classmethod
    async def resolve(cls, session: AsyncSession, *, staff_user_id: int, tenant_id: int | None = None):
        candidates = await cls.candidates(session, staff_user_id=staff_user_id)
        if tenant_id is not None:
            candidates = [row for row in candidates if row.tenant_id == tenant_id]
        if len(candidates) != 1:
            code = "company_selection_required" if tenant_id is None and len(candidates) > 1 else "company_access_denied"
            raise ManagerTenantAccessResolutionError("Active tenant membership is missing or ambiguous", code=code)
        return cls._access(candidates[0])

    @classmethod
    async def personal(cls, session, *, staff_user_id):
        """An actual membership for personal audit/login, never virtual support."""
        candidates = await cls.candidates(session, staff_user_id=staff_user_id)
        if not candidates:
            raise ManagerTenantAccessResolutionError("Active workspace membership required")
        candidate = sorted(candidates, key=lambda row: (row.demo_read_only, row.membership_id))[0]
        if sum(row.tenant_id == candidate.tenant_id for row in candidates) != 1:
            raise ManagerTenantAccessResolutionError("Default storefront is ambiguous")
        return cls._access(candidate)

    @staticmethod
    async def platform_support(session, *, tenant_id):
        """Caller must prove live platform authority; this never creates membership."""
        rows = await TenancyDAO.active_company_defaults(session, tenant_id=tenant_id)
        if len(rows) != 1:
            raise ManagerTenantAccessResolutionError("Active company default storefront required")
        tenant, storefront = rows[0]
        return ManagerTenantAccess(None, "owner", TenantScope(
            tenant_id=tenant.id, storefront_id=storefront.id, is_system=tenant.is_system,
            demo_read_only=tenant.demo_read_only,
        ), access_kind="platform_support")
