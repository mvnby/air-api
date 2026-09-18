from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.yandex_business import YandexBusinessFeedSettings, utc_now
from models.tenancy import TenantScope
from services.tenant_scope_service import storefront_scope_clause


@dataclass(frozen=True)
class YandexBusinessFeedConfiguration:
    selection_mode: str = "all_published"
    include_services: bool = True
    require_ready_image: bool = False
    require_in_stock: bool = False


class YandexBusinessFeedSettingsService:
    @staticmethod
    def defaults() -> YandexBusinessFeedConfiguration:
        return YandexBusinessFeedConfiguration()

    @staticmethod
    async def get(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> YandexBusinessFeedConfiguration:
        setting = (
            await session.execute(
                select(YandexBusinessFeedSettings).where(
                    storefront_scope_clause(YandexBusinessFeedSettings, tenant_scope)
                )
            )
        ).scalar_one_or_none()
        if setting is None:
            return YandexBusinessFeedSettingsService.defaults()
        return YandexBusinessFeedConfiguration(
            selection_mode=setting.selection_mode,
            include_services=setting.include_services,
            require_ready_image=setting.require_ready_image,
            require_in_stock=setting.require_in_stock,
        )

    @staticmethod
    async def update(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        configuration: YandexBusinessFeedConfiguration,
    ) -> YandexBusinessFeedConfiguration:
        setting = (
            await session.execute(
                select(YandexBusinessFeedSettings).where(
                    storefront_scope_clause(YandexBusinessFeedSettings, tenant_scope)
                )
            )
        ).scalar_one_or_none()
        if setting is None:
            setting = YandexBusinessFeedSettings(
                tenant_id=tenant_scope.tenant_id,
                storefront_id=tenant_scope.storefront_id,
            )
        setting.selection_mode = configuration.selection_mode
        setting.include_services = configuration.include_services
        setting.require_ready_image = configuration.require_ready_image
        setting.require_in_stock = configuration.require_in_stock
        setting.updated_at = utc_now()
        session.add(setting)
        await session.commit()
        return configuration
