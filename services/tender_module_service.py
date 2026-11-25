"""Versioned company tender preferences and audited platform entitlement."""

import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from core.request_context import current_request_id
from core.security import AuthenticatedIdentity, AuthenticatedUser
from crud.platform_companies import PlatformCompaniesDAO
from crud.tender_module import TenderModuleDAO
from models import TenantAuditEvent, TenantTenderModule
from schemas_tender_search import (
    TenderModuleEntitlementUpdate, TenderModuleSettings, TenderModuleUpdate, TenderProfilePreview, TenderSearchProfile,
)
from services.legacy_owner_auth_state_service import LegacyOwnerAuthStateService
from services.legacy_owner_managed_identity_service import LegacyOwnerManagedIdentityService
from services.tender_profile_preview import preview_tender_profile


class TenderModuleError(ValueError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def _project(row: TenantTenderModule | None) -> TenderModuleSettings:
    if row is None:
        return TenderModuleSettings(entitled=False, enabled=False, version=0)
    return TenderModuleSettings(
        entitled=row.entitled, enabled=row.enabled, version=row.version, profiles=row.profiles,
    )


def _require_version(current: TenderModuleSettings, expected: int) -> None:
    if current.version != expected:
        raise TenderModuleError(409, "Настройки тендеров уже изменены. Обновите страницу.")


class TenderModuleService:
    @staticmethod
    async def get(session: AsyncSession, tenant_id: int) -> TenderModuleSettings:
        return _project(await TenderModuleDAO.get(session, tenant_id))

    @staticmethod
    async def get_company_access(session: AsyncSession, tenant_id: int) -> TenderModuleSettings:
        if await PlatformCompaniesDAO.get_tenant(session, tenant_id) is None:
            raise TenderModuleError(404, "Компания не найдена.")
        return await TenderModuleService.get(session, tenant_id)

    @staticmethod
    async def preview(
        session: AsyncSession, actor: AuthenticatedUser, profile: TenderSearchProfile,
    ) -> TenderProfilePreview:
        scope = actor.tenant_scope()
        access = await TenderModuleService.get(session, scope.tenant_id)
        if not access.entitled or scope.demo_read_only:
            raise TenderModuleError(403, "Настройка поиска тендеров для компании недоступна.")
        rows = await TenderModuleDAO.recent_orders(session, scope)
        return await asyncio.to_thread(preview_tender_profile, rows, profile)

    @staticmethod
    async def update(
        session: AsyncSession, actor: AuthenticatedUser, payload: TenderModuleUpdate,
    ) -> TenderModuleSettings:
        scope = actor.tenant_scope()
        # Lock the same parent for configuration and entitlement changes.
        tenant = await PlatformCompaniesDAO.get_tenant(session, scope.tenant_id, lock=True)
        if tenant is None or tenant.status != "active" or tenant.demo_read_only or scope.demo_read_only:
            raise TenderModuleError(403, "Настройки тендеров недоступны для этой компании.")
        row = await TenderModuleDAO.get(session, scope.tenant_id)
        current = _project(row)
        if row is None or not row.entitled:
            raise TenderModuleError(403, "Подключение тендеров для компании недоступно.")
        _require_version(current, payload.version)
        if current.enabled == payload.enabled and current.profiles == payload.profiles:
            return current
        row.enabled = payload.enabled
        row.profiles = [profile.model_dump(mode="json") for profile in payload.profiles]
        await TenderModuleService._save(
            session, row, current, actor, scope.storefront_id, "tender_module.settings.updated",
        )
        return _project(row)

    @staticmethod
    async def set_entitlement(
        session: AsyncSession, tenant_id: int, actor: AuthenticatedIdentity, payload: TenderModuleEntitlementUpdate,
    ) -> TenderModuleSettings:
        auth_state = await LegacyOwnerAuthStateService.get(session, for_update=True)
        tenant = await PlatformCompaniesDAO.get_tenant(session, tenant_id, lock=True)
        staff = await PlatformCompaniesDAO.lock_staff(session, actor.staff_user_id) if actor.staff_user_id else None
        if (not actor.is_platform_owner or staff is None or staff.status != "active"
                or staff.merged_into_staff_user_id is not None or actor.auth_version != staff.auth_version
                or not await LegacyOwnerManagedIdentityService.exact_bound_staff_identity_allowed(
                    session, state=auth_state, user=staff,
                )):
            raise TenderModuleError(401, "Доступ владельца платформы изменился. Войдите повторно.")
        if tenant is None:
            raise TenderModuleError(404, "Компания не найдена.")
        if payload.entitled and (tenant.status != "active" or tenant.demo_read_only):
            raise TenderModuleError(409, "Подключение тендеров доступно для действующей компании.")
        row = await TenderModuleDAO.get(session, tenant_id)
        current = _project(row)
        _require_version(current, payload.version)
        if current.entitled == payload.entitled:
            return current
        storefront_id = await TenderModuleDAO.default_storefront_id(session, tenant_id)
        if storefront_id is None:
            raise TenderModuleError(409, "У компании не настроена основная витрина.")
        row = row if row is not None else TenantTenderModule(tenant_id=tenant_id)
        row.entitled = payload.entitled
        if not row.entitled:
            row.enabled = False
        await TenderModuleService._save(
            session, row, current, actor, storefront_id, "tender_module.entitlement.updated",
        )
        return _project(row)

    @staticmethod
    async def _save(session, row, before, actor, storefront_id, action) -> None:
        row.version = before.version + 1
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.add(TenantAuditEvent(
            tenant_id=row.tenant_id, storefront_id=storefront_id, actor_staff_user_id=actor.staff_user_id,
            actor_username=actor.username, entity_type="tenant_tender_module", entity_id=row.tenant_id,
            action=action, request_id=current_request_id(),
            change_set={"before": before.model_dump(mode="json"), "after": _project(row).model_dump(mode="json")},
        ))
        await session.commit()
