from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import GlobalConfig, Storefront
from models.storefront_settings import StorefrontSettings
from models.tenancy import TenantScope


class StorefrontSettingsDAO:
    @staticmethod
    async def get_storefront(session: AsyncSession, scope: TenantScope, *, for_update: bool = False) -> Storefront | None:
        statement = select(Storefront).where(Storefront.id == scope.storefront_id, Storefront.tenant_id == scope.tenant_id)
        if for_update:
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def get(session: AsyncSession, scope: TenantScope) -> StorefrontSettings | None:
        return (await session.execute(select(StorefrontSettings).where(
            StorefrontSettings.storefront_id == scope.storefront_id,
            StorefrontSettings.tenant_id == scope.tenant_id,
        ))).scalar_one_or_none()

    @staticmethod
    async def canonical_contacts(session: AsyncSession) -> dict[str, str]:
        keys = {"phone", "email", "address", "work_hours"}
        rows = (await session.execute(select(GlobalConfig).where(GlobalConfig.key.in_(keys)))).scalars().all()
        return {row.key: row.value for row in rows}
