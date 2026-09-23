"""Partner-facing settings; never expose or edit platform configuration."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.request_context import current_request_id
from crud.catalog_revision import CatalogRevisionDAO
from crud.storefront_settings import StorefrontSettingsDAO
from models import MediaAsset, TenantAuditEvent
from models.storefront_settings import StorefrontSettings
from models.tenancy import TenantScope
from schemas_storefront_settings import (
    SERVICE_DIRECTIONS,
    StorefrontSettingsPayload,
    StorefrontSettingsResponse,
    StorefrontSiteSettings,
    StorefrontSiteSettingsResponse,
    default_service_directions,
)
from services.catalog_revision_service import CatalogRevisionService


class StorefrontSettingsService:
    @staticmethod
    async def _response(session: AsyncSession, row: StorefrontSettings) -> StorefrontSettingsResponse:
        ids = [asset_id for asset_id in (row.logo_asset_id, row.compact_logo_asset_id) if asset_id]
        assets = (await session.execute(select(MediaAsset).where(
            MediaAsset.id.in_(ids),
            MediaAsset.tenant_id == row.tenant_id,
            MediaAsset.storefront_id == row.storefront_id,
            MediaAsset.kind == "storefront_logo",
            MediaAsset.processing_status == "ready",
        ))).scalars().all() if ids else []
        urls = {asset.id: asset.url for asset in assets}
        return StorefrontSettingsResponse(
            site=StorefrontSiteSettingsResponse(
                **{key: getattr(row, key) for key in StorefrontSiteSettings.model_fields},
                logo_url=urls.get(row.logo_asset_id),
                compact_logo_url=urls.get(row.compact_logo_asset_id),
            ),
            services=row.services,
            version=row.version,
            updated_at=row.updated_at,
        )

    @classmethod
    async def get_settings(cls, session: AsyncSession, *, tenant_scope: TenantScope) -> StorefrontSettingsResponse:
        storefront = await StorefrontSettingsDAO.get_storefront(session, tenant_scope)
        if storefront is None:
            raise HTTPException(status_code=404, detail="Витрина не найдена")
        row = await StorefrontSettingsDAO.get(session, tenant_scope)
        if row is not None:
            return await cls._response(session, row)
        canonical = tenant_scope.is_system and storefront.is_default
        contacts = await StorefrontSettingsDAO.canonical_contacts(session) if canonical else {}
        return StorefrontSettingsResponse(
            site=StorefrontSiteSettingsResponse(display_name=storefront.display_name, city=storefront.city or "", **contacts),
            services=default_service_directions(enabled=canonical),
            version=0,
        )

    @classmethod
    async def is_service_enabled(cls, session: AsyncSession, *, tenant_scope: TenantScope, service_kind: str) -> bool:
        if service_kind not in SERVICE_DIRECTIONS:
            return False
        result = await cls.get_settings(session, tenant_scope=tenant_scope)
        return any(item.key == service_kind and item.enabled for item in result.services)

    @classmethod
    async def update_settings(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        payload: StorefrontSettingsPayload,
        actor_username: str,
        actor_staff_user_id: int | None,
        commit: bool = True,
    ) -> StorefrontSettingsResponse:
        # Lock the parent even for the first save, making concurrent inserts and
        # updates share the same optimistic version boundary.
        storefront = await StorefrontSettingsDAO.get_storefront(session, tenant_scope, for_update=True)
        if storefront is None:
            raise HTTPException(status_code=404, detail="Витрина не найдена")
        row = await StorefrontSettingsDAO.get(session, tenant_scope)
        current = await cls.get_settings(session, tenant_scope=tenant_scope)
        if payload.version != current.version:
            raise HTTPException(status_code=409, detail="Настройки уже изменены. Обновите страницу и повторите правку.")
        ids = {asset_id for asset_id in (payload.site.logo_asset_id, payload.site.compact_logo_asset_id) if asset_id}
        if ids:
            allowed = (await session.execute(select(MediaAsset.id).where(
                MediaAsset.id.in_(ids),
                MediaAsset.tenant_id == tenant_scope.tenant_id,
                MediaAsset.storefront_id == tenant_scope.storefront_id,
                MediaAsset.kind == "storefront_logo",
                MediaAsset.processing_status == "ready",
            ))).scalars().all()
            if set(allowed) != ids:
                raise HTTPException(status_code=422, detail="Логотип должен быть загружен для этой витрины")
        data = payload.model_dump(exclude={"version"})
        before = current.model_dump(exclude={"version": True, "updated_at": True, "site": {"logo_url", "compact_logo_url"}})
        if row is not None and data == before:
            if commit:
                await session.commit()
            return current
        if row is None:
            row = StorefrontSettings(tenant_id=tenant_scope.tenant_id, storefront_id=tenant_scope.storefront_id, display_name=payload.site.display_name)
        for key, value in payload.site.model_dump().items():
            setattr(row, key, value)
        row.services = [item.model_dump() for item in payload.services]
        row.version = current.version + 1
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.add(TenantAuditEvent(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            actor_username=actor_username,
            actor_staff_user_id=actor_staff_user_id,
            action="storefront.settings.updated",
            entity_type="storefront_settings",
            entity_id=tenant_scope.storefront_id,
            request_id=current_request_id(),
            change_set={"before": before, "after": data, "version": row.version},
        ))
        if await CatalogRevisionDAO.list_invalidation_targets(session, tenant_scope=tenant_scope):
            await CatalogRevisionService.stage_invalidation(
                session,
                reason="storefront_settings_updated",
                tenant_scope=tenant_scope,
                additional_paths=["/", "/services/", "/montaj-konditionerov/", "/obslujivanie-kondicionerov/", "/services/repair/", "/services/zakladka-kommunikaciy-kondicionera/", "/services/demontazh-kondicionera/"],
            )
        if commit:
            await session.commit()
        else:
            await session.flush()
        await session.refresh(row)
        return await cls._response(session, row)
