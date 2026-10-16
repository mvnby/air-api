from __future__ import annotations

from core.security import AuthenticatedUser, MANAGER_ACCESS_ROLES, OWNER_ACCESS_ROLES
from core.call_recording_access import has_call_recording_pilot_access


class ManagerCapabilityService:
    """Derive the manager UI contract from server-verified authorization state."""

    CRM_MANAGE = "crm.manage"
    CATALOG_MASTER_READ = "catalog.master.read"
    CATALOG_MASTER_EDIT = "catalog.master.edit"
    CATALOG_MASTER_DELETE = "catalog.master.delete"
    STOREFRONT_OFFERS_READ = "storefront.offers.read"
    STOREFRONT_COLLECTIONS_MANAGE = "storefront.collections.manage"
    PLATFORM_MANAGE = "platform.manage"
    PLATFORM_COMPANIES_MANAGE = "platform.companies.manage"
    STAFF_MANAGE = "staff.manage"
    INFRASTRUCTURE_MANAGE = "infrastructure.manage"
    ANALYTICS_MANAGE = "analytics.manage"
    DOCUMENTS_MANAGE = "documents.manage"
    SETTINGS_MANAGE = "settings.manage"
    SERVICES_MANAGE = "services.manage"
    CALL_RECORDINGS_MANAGE = "call_recordings.manage"

    ORDERED_CAPABILITIES = (
        CRM_MANAGE,
        CATALOG_MASTER_READ,
        CATALOG_MASTER_EDIT,
        CATALOG_MASTER_DELETE,
        STOREFRONT_OFFERS_READ,
        STOREFRONT_COLLECTIONS_MANAGE,
        PLATFORM_MANAGE,
        PLATFORM_COMPANIES_MANAGE,
        STAFF_MANAGE,
        INFRASTRUCTURE_MANAGE,
        ANALYTICS_MANAGE,
        DOCUMENTS_MANAGE,
        SETTINGS_MANAGE,
        SERVICES_MANAGE,
        CALL_RECORDINGS_MANAGE,
    )

    @classmethod
    def for_auth(cls, auth: AuthenticatedUser) -> list[str]:
        role = str(auth.role or "").strip().lower()
        capabilities: set[str] = set()
        if role in MANAGER_ACCESS_ROLES:
            if has_call_recording_pilot_access(auth.staff_user_id):
                capabilities.add(cls.CALL_RECORDINGS_MANAGE)
            capabilities.update(
                {
                    cls.CRM_MANAGE,
                    cls.CATALOG_MASTER_READ,
                    cls.STOREFRONT_OFFERS_READ,
                    cls.STOREFRONT_COLLECTIONS_MANAGE,
                    cls.SERVICES_MANAGE,
                }
            )
        if auth.is_platform_owner:
            capabilities.add(cls.PLATFORM_COMPANIES_MANAGE)
            if auth.is_system_tenant:
                capabilities.add(cls.PLATFORM_MANAGE)
                capabilities.add(cls.INFRASTRUCTURE_MANAGE)
        if auth.is_platform_owner or cls.CATALOG_MASTER_EDIT in auth.permissions:
            capabilities.update({cls.CATALOG_MASTER_READ, cls.CATALOG_MASTER_EDIT})
            if auth.is_platform_owner or cls.CATALOG_MASTER_DELETE in auth.permissions:
                capabilities.add(cls.CATALOG_MASTER_DELETE)
        if role in OWNER_ACCESS_ROLES:
            capabilities.add(cls.STAFF_MANAGE)
            capabilities.add(cls.ANALYTICS_MANAGE)
            capabilities.add(cls.DOCUMENTS_MANAGE)
            capabilities.add(cls.SETTINGS_MANAGE)
        return [
            capability
            for capability in cls.ORDERED_CAPABILITIES
            if capability in capabilities
        ]
