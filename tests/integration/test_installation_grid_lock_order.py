"""Partner initialization and grid reset must not form an ABBA lock cycle."""

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from models import InstallationPriceBook, ServiceTariff, Storefront, Tenant
from services.installation_grid_rollout import (
    InstallationGridPlanToken, InstallationGridRolloutService,
)
from services.partner_site_setup_service import (
    PartnerSiteSetupManifest, PartnerSiteSetupPlanToken, PartnerSiteSetupService,
)
from services.storefront_onboarding_state import StorefrontOnboardingBlockedError


@pytest.mark.asyncio
async def test_partner_initialization_then_grid_apply_serializes_without_deadlock(
    db_engine, monkeypatch,
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
        seed.add_all([
            storefront,
            ServiceTariff(service_kind="installation", selector_label="Old source",
                          installation_code="installation.old.gridlock",
                          installation_match={"indoor_type": "wall"},
                          category="Wall", power_range="07,09,12", base_price=500),
            InstallationPriceBook(tenant_id=system.id, revision=1,
                                  fingerprint="approved-source", entries=[]),
        ])
        await seed.commit()

    async def source_fingerprint(_session, _scope):
        return "approved-source"

    async def fake_publish(session, scope, *, actor, commit):
        assert commit is False
        # Match the publication mutex: both partner initialization and the
        # rollout must acquire Tenant before touching the price-book row.
        await session.execute(select(Tenant).where(
            Tenant.id == scope.tenant_id,
        ).with_for_update(key_share=True))
        book = InstallationPriceBook(tenant_id=scope.tenant_id, revision=1,
                                     fingerprint=f"own-{scope.tenant_id}", entries=[],
                                     published_by=actor)
        session.add(book)
        await session.flush()
        return SimpleNamespace(price_book_id=book.id, revision=book.revision,
                               fingerprint=book.fingerprint)

    monkeypatch.setattr(
        "services.service_catalog_template_service.InstallationPriceBookService.current_draft_fingerprint",
        source_fingerprint, raising=False,
    )
    monkeypatch.setattr(
        "services.service_catalog_template_service.InstallationPriceBookService.publish",
        fake_publish,
    )
    monkeypatch.setattr("services.installation_grid_rollout._validate_seed_against_installed_contract",
                        lambda: None)
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
        assert rows[0].installation_code == "installation.old.gridlock"
