"""Retire new legacy installation estimates once a scoped price book is live."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import ServiceTariff, Tenant
from models.tenancy import TenantScope


class LegacyInstallationEstimatePolicy:
    @staticmethod
    async def book_is_published(session: AsyncSession, scope: TenantScope) -> bool:
        # Local import avoids a cycle: the book resolver reuses legacy line builders.
        from services.installation_price_book_service import InstallationPriceBookService

        return await InstallationPriceBookService.latest(session, scope) is not None

    @classmethod
    async def require_available(
        cls, session: AsyncSession, scope: TenantScope | None,
        tariff: ServiceTariff, *, serialize_write: bool = False,
    ) -> None:
        if scope is None or tariff.service_kind != "installation":
            return
        if serialize_write:
            # Publication takes this same lock. Keep it until the estimate
            # commit so the first book cannot appear mid-write.
            await session.execute(
                select(Tenant).where(Tenant.id == scope.tenant_id)
                .with_for_update(key_share=True)
            )
        if await cls.book_is_published(session, scope):
            raise HTTPException(status_code=409, detail={
                "code": "book_preview_required",
                "message": "Use the installation price book in the order proposal",
            })
