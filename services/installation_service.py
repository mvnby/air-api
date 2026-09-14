import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import InstallationRate
from models.tenancy import TenantScope
from services.service_catalog_scope import (
    canonical_service_catalog_clause,
    service_catalog_scope_clause,
)

logger = logging.getLogger(__name__)


class InstallationService:
    @staticmethod
    async def get_all(
        session: AsyncSession,
        tenant_scope: TenantScope | None = None,
    ):
        scope_clause = (
            canonical_service_catalog_clause(InstallationRate)
            if tenant_scope is None
            else service_catalog_scope_clause(InstallationRate, tenant_scope)
        )
        stmt = (
            select(InstallationRate)
            .where(scope_clause)
            .order_by(InstallationRate.id)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def seed_defaults(session: AsyncSession):
        """Populate initial installation rates if table is empty."""
        stmt = select(InstallationRate).where(
            canonical_service_catalog_clause(InstallationRate)
        )
        result = await session.execute(stmt)
        existing = result.first()

        if existing:
            return

        logger.info("Seeding default installation rates...")

        defaults = [
            # Wall Mounted
            InstallationRate(
                category="Wall",
                power_range="07-12",
                base_price=600,
                extra_pipe_price=50,
                is_fixed=True,
            ),
            InstallationRate(
                category="Wall",
                power_range="18-24",
                base_price=750,
                extra_pipe_price=65,
                is_fixed=True,
            ),
            InstallationRate(
                category="Wall",
                power_range="30-36",
                base_price=960,
                extra_pipe_price=85,
                is_fixed=True,
            ),
            # Others
            InstallationRate(
                category="Cassette",
                power_range="All",
                base_price=1500,
                extra_pipe_price=0,
                is_fixed=False,
                comment="Price starts from...",
            ),
            InstallationRate(
                category="Duct",
                power_range="All",
                base_price=1500,
                extra_pipe_price=0,
                is_fixed=False,
                comment="Price starts from...",
            ),
            InstallationRate(
                category="Ceiling",
                power_range="All",
                base_price=1400,
                extra_pipe_price=0,
                is_fixed=False,
                comment="Price starts from...",
            ),
        ]

        for rate in defaults:
            session.add(rate)

        await session.commit()
        logger.info("Seeded %s installation rates.", len(defaults))
