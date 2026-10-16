"""Company bootstrap reads the person, never the browser's selected scope."""
from collections import Counter
from crud.tenancy import TenancyDAO
from services.manager_tenant_access_service import ManagerTenantAccessResolver


class ManagerAccountCompaniesService:
    @staticmethod
    async def list(session, *, identity, page, limit):
        actual = await ManagerTenantAccessResolver.candidates(session, staff_user_id=identity.staff_user_id) if identity.staff_user_id else []
        counts = Counter(row.tenant_id for row in actual)
        actual = {row.tenant_id: row for row in actual if counts[row.tenant_id] == 1}
        defaults = await TenancyDAO.active_company_defaults(session, tenant_ids=None if identity.is_platform_owner else list(actual))
        counts = Counter(tenant.id for tenant, _ in defaults)
        items = []
        for tenant, site in defaults:
            membership = actual.get(tenant.id)
            if counts[tenant.id] != 1 or (membership is None and not identity.is_platform_owner):
                continue
            items.append({
                "tenant_id": tenant.id, "slug": tenant.slug, "display_name": tenant.display_name,
                "role": membership.role if membership else "owner",
                "membership_id": membership.membership_id if membership else None,
                "access_kind": "membership" if membership else "platform_support",
                "is_system": tenant.is_system, "demo_read_only": tenant.demo_read_only,
                "default_storefront_slug": site.slug,
            })
        default = next(iter(actual)) if len(actual) == 1 else None
        if identity.is_platform_owner and identity.staff_user_id is None:
            default = next((item["tenant_id"] for item in items if item["is_system"] and item["slug"] == "mvn"), None)
        return {"staff_user_id": identity.staff_user_id, "username": identity.username,
                "is_platform_owner": identity.is_platform_owner, "default_tenant_id": default,
                "items": items[(page - 1) * limit:page * limit], "total": len(items), "page": page, "limit": limit}
