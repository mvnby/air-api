"""Visible companies/sites and narrowly scoped, audited company controls."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.manager_platform_companies import (
    CompanyDomainResponse, CompanySiteResponse, CompanySitesResponse,
    PlatformCompanyListResponse, PlatformCompanyResponse, PlatformCompanyUpdate,
)
from core.request_context import current_request_id
from crud.platform_companies import PlatformCompaniesDAO
from models import TenantAuditEvent
from services.legacy_owner_auth_state_service import LegacyOwnerAuthStateService
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class PlatformCompanyError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code, self.status_code = code, status_code


class PlatformCompaniesService:
    @staticmethod
    def sites(rows, domains):
        return [CompanySiteResponse(
            id=site.id, slug=site.slug, display_name=site.display_name, status=site.status,
            city=site.city, default_locale=site.default_locale, currency=site.currency,
            is_default=site.is_default,
            domains=[CompanyDomainResponse(id=domain.id, hostname=domain.hostname,
                status=domain.status, is_primary=domain.is_primary,
                verified_at=utc(domain.verified_at) if domain.verified_at else None)
                for domain in domains[site.id]],
        ) for site in rows]

    @classmethod
    async def project(cls, session: AsyncSession, tenants):
        sites, domains, owners, counts = await PlatformCompaniesDAO.details(session, [row.id for row in tenants])
        return [PlatformCompanyResponse(
            id=row.id, slug=row.slug, display_name=row.display_name, kind=row.kind, status=row.status,
            is_system=row.is_system, demo_read_only=row.demo_read_only, updated_at=utc(row.updated_at),
            owners=owners[row.id], active_staff_count=counts.get(row.id, 0),
            sites=cls.sites(sites[row.id], domains),
        ) for row in tenants]

    @classmethod
    async def list(cls, session: AsyncSession, *, page: int, limit: int, search: str | None):
        tenants, total = await PlatformCompaniesDAO.list_tenants(session, page=page, limit=limit, search=search)
        return PlatformCompanyListResponse(items=await cls.project(session, tenants), total=total, page=page, limit=limit)

    @classmethod
    async def own_sites(cls, session: AsyncSession, *, tenant_id: int, page: int, limit: int):
        sites, domains, _, _ = await PlatformCompaniesDAO.details(session, [tenant_id])
        rows = sites[tenant_id]
        return CompanySitesResponse(items=cls.sites(rows[(page - 1) * limit:page * limit], domains),
                                    total=len(rows), page=page, limit=limit)

    @classmethod
    async def update(cls, session: AsyncSession, *, tenant_id: int, payload: PlatformCompanyUpdate, actor):
        # Serialize with owner recovery/profile writes and tenant staff administration.
        state = await LegacyOwnerAuthStateService.get(session, for_update=True)
        tenant = await PlatformCompaniesDAO.get_tenant(session, tenant_id, lock=True)
        staff = await PlatformCompaniesDAO.lock_staff(session, actor.staff_user_id) if actor.staff_user_id else None
        if (not actor.is_platform_owner or staff is None or staff.status != "active"
                or staff.merged_into_staff_user_id is not None or actor.auth_version != staff.auth_version
                or not await LegacyOwnerManagedIdentityService.exact_bound_staff_identity_allowed(session, state=state, user=staff)):
            raise PlatformCompanyError("platform_access_changed", "Войдите в систему повторно", 401)
        if tenant is None:
            raise PlatformCompanyError("company_not_found", "Компания не найдена", 404)
        if utc(tenant.updated_at) != utc(payload.expected_updated_at):
            raise PlatformCompanyError("company_changed", "Данные компании уже изменены. Обновите список")
        if (tenant.is_system or tenant.slug == "mvn") and payload.status == "disabled":
            raise PlatformCompanyError("system_company_protected", "Основную компанию системы нельзя отключить")
        changes = {}
        for field in payload.model_fields_set - {"expected_updated_at"}:
            before, after = getattr(tenant, field), getattr(payload, field)
            if before != after:
                changes[field] = {"before": before, "after": after}
                setattr(tenant, field, after)
        if changes:
            sites, _, _, _ = await PlatformCompaniesDAO.details(session, [tenant_id])
            default = next((site for site in sites[tenant_id] if site.is_default), None)
            if default is None:
                raise PlatformCompanyError("company_site_missing", "У компании не настроен основной сайт")
            tenant.updated_at = datetime.now(timezone.utc)
            session.add(tenant)
            session.add(TenantAuditEvent(
                tenant_id=tenant_id, storefront_id=default.id, actor_staff_user_id=staff.id,
                actor_username=actor.username, request_id=current_request_id(),
                action="company.updated", entity_type="tenant", entity_id=tenant_id, change_set=changes,
            ))
            await session.flush()
        response = (await cls.project(session, [tenant]))[0]
        await session.commit()
        return response
