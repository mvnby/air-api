from __future__ import annotations

from core.security import AuthenticatedUser, MANAGER_ACCESS_ROLES, OWNER_ACCESS_ROLES


class ManagerCapabilityService:
    """Derive the manager UI contract from server-verified authorization state."""

    CRM_MANAGE = "crm.manage"
    CATALOG_MASTER_READ = "catalog.master.read"
    STOREFRONT_OFFERS_READ = "storefront.offers.read"
    PLATFORM_MANAGE = "platform.manage"
    STAFF_MANAGE = "staff.manage"
    INFRASTRUCTURE_MANAGE = "infrastructure.manage"

    ORDERED_CAPABILITIES = (
        CRM_MANAGE,
        CATALOG_MASTER_READ,
        STOREFRONT_OFFERS_READ,
        PLATFORM_MANAGE,
        STAFF_MANAGE,
        INFRASTRUCTURE_MANAGE,
    )

    @classmethod
    def for_auth(cls, auth: AuthenticatedUser) -> list[str]:
        role = str(auth.role or "").strip().lower()
        capabilities: set[str] = set()
        if role in MANAGER_ACCESS_ROLES:
            capabilities.update(
                {
                    cls.CRM_MANAGE,
                    cls.CATALOG_MASTER_READ,
                    cls.STOREFRONT_OFFERS_READ,
                }
            )
        if auth.is_system_tenant:
            capabilities.add(cls.PLATFORM_MANAGE)
        if role in OWNER_ACCESS_ROLES:
            capabilities.add(cls.STAFF_MANAGE)
            if auth.is_system_tenant:
                capabilities.add(cls.INFRASTRUCTURE_MANAGE)
        return [
            capability
            for capability in cls.ORDERED_CAPABILITIES
            if capability in capabilities
        ]
