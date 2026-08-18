"""Deprecated Orsha DAO compatibility over the generic onboarding DAO."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from crud.storefront_onboarding import StorefrontOnboardingDAO


class OrshaStorefrontBootstrapDAO(StorefrontOnboardingDAO):
    @staticmethod
    async def try_acquire_transaction_lock(session: AsyncSession) -> bool:
        return await StorefrontOnboardingDAO.try_acquire_transaction_locks(
            session,
            tenant_slug="mvn",
            storefront_slug="orsha",
            hostname="orsha-internal.mvn.by",
        )


__all__ = ["OrshaStorefrontBootstrapDAO"]
