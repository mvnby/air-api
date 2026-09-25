"""Partner initialization and grid reset must not form an ABBA lock cycle."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import InstallationPriceBook, ServiceTariff, ServiceTariffRule, Storefront, Tenant
from models.tenancy import TenantScope
from services.installation_grid_rollout import (
    InstallationGridPlanToken, InstallationGridRolloutService,
)
from services.installation_grid_seed import canonical_installation_grid
from services.installation_price_book_service import InstallationPriceBookService
from services.partner_site_setup_service import (
    PartnerSiteSetupManifest, PartnerSiteSetupPlanToken, PartnerSiteSetupService,
)
from services.storefront_onboarding_state import StorefrontOnboardingBlockedError


@pytest.mark.asyncio
async def test_partner_initialization_then_grid_apply_serializes_without_deadlock(
    db_engine,
):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as seed:
        system = (await seed.execute(select(Tenant).where(Tenant.is_system.is_(True)))).scalar_one()
        partner = Tenant(slug="grid-lock-partner", display_name="Grid lock partner")
        seed.add(partner)
        await seed.flush()
        storefront = Storefront(tenant_id=partner.id, slug="main",
                                display_name="Partner", status="active", is_default=True)
        seed.add(storefront)
        source_spec = canonical_installation_grid()[0]
        source = ServiceTariff(**source_spec.fields())
        seed.add(source)
        await seed.flush()
        seed.add_all(ServiceTariffRule(
            tariff_id=source.id, sort_order=index * 10, **rule.fields(),
        ) for index, rule in enumerate(source_spec.rules))
        await seed.flush()
        await InstallationPriceBookService.publish(
            seed, TenantScope(tenant_id=system.id, storefront_id=1, is_system=True),
            actor="test:grid-lock-source", commit=False,
        )
        await seed.commit()
    manifest = PartnerSiteSetupManifest(
        tenant_slug="grid-lock-partner", storefront_slug="main",
        site={"display_name": "Partner"}, enabled_services=["installation"],
    )
    proofs = dict(
        expected_partner_slugs=("grid-lock-partner",),
        backend_release_commit="b" * 40,
        backend_image_digest="sha256:" + "c" * 64,
        web_v2_commit="a" * 40,
        web_v2_proof="https://github.com/mvnby/mvn-web/actions/runs/1",
        manager_editor_proof="https://github.com/mvnby/air-api/actions/runs/2",
        legacy_list_proof="https://github.com/mvnby/air-api/actions/runs/5",
        legacy_calculate_proof="https://github.com/mvnby/air-api/actions/runs/3",
        legacy_tariff_calculate_proof="https://github.com/mvnby/air-api/actions/runs/4",
        include_demo_reset=False,
    )
    async with factory() as review:
        partner_plan, _ = await PartnerSiteSetupService.plan(review, manifest)
        assert partner_plan["blockers"] == []
        partner_token = PartnerSiteSetupPlanToken.issue(
            plan_digest=partner_plan["plan_digest"],
        )
        grid_plan, _ = await InstallationGridRolloutService.plan(review, **proofs)
        assert grid_plan["blockers"] == []
        grid_token = InstallationGridPlanToken.issue(
            plan_digest=grid_plan["plan_digest"],
        )

    locked = asyncio.Event()
    release = asyncio.Event()

    async def initialize_partner():
        async with factory() as session:
            async with session.begin():
                await session.execute(text("SET LOCAL lock_timeout = '4s'"))
                await PartnerSiteSetupService.plan(session, manifest, lock=True)
                locked.set()
                await release.wait()
                await PartnerSiteSetupService.execute(
                    session, manifest, plan_token=partner_token,
                )

    async def attempt_grid_reset():
        await locked.wait()
        try:
            async with factory() as session:
                async with session.begin():
                    await session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
                    await session.execute(text("SET LOCAL lock_timeout = '4s'"))
                    await InstallationGridRolloutService.apply(
                        session, **proofs, plan_token=grid_token,
                    )
        except StorefrontOnboardingBlockedError:
            return "stale_plan"
        except DBAPIError as exc:
            # An optimistic serializable retry rolls back safely; a deadlock
            # or book uniqueness race means the lock protocol regressed.
            assert getattr(exc.orig, "sqlstate", None) == "40001"
            return "safe_retry"
        raise AssertionError("Stale grid plan unexpectedly applied")

    init_task = asyncio.create_task(initialize_partner())
    await asyncio.wait_for(locked.wait(), timeout=5)
    reset_task = asyncio.create_task(attempt_grid_reset())
    await asyncio.sleep(0.1)
    release.set()
    await asyncio.wait_for(init_task, timeout=10)
    assert await asyncio.wait_for(reset_task, timeout=10) in {
        "stale_plan", "safe_retry",
    }
    async with factory() as verify:
        rows = list((await verify.execute(select(ServiceTariff).where(
            ServiceTariff.tenant_id == partner.id,
        ))).scalars().all())
        assert len(rows) == 1
        assert rows[0].installation_code == source_spec.code
        partner_books = list((await verify.execute(select(InstallationPriceBook).where(
            InstallationPriceBook.tenant_id == partner.id,
        ))).scalars().all())
        assert len(partner_books) == 1
