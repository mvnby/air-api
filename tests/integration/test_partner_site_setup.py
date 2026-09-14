import pytest
from sqlmodel import select

from models import ServiceTariff, Storefront, Tenant
from models.storefront_settings import StorefrontSettings
from services.partner_site_setup_service import (
    PartnerSiteSetupManifest, PartnerSiteSetupPlanToken, PartnerSiteSetupService,
)
from services.storefront_onboarding_state import StorefrontOnboardingBlockedError


async def seed(db):
    tenant = Tenant(slug="setup-partner", display_name="Partner", is_system=False)
    db.add(tenant)
    await db.flush()
    storefront = Storefront(tenant_id=tenant.id, slug="main", display_name="Partner")
    source = ServiceTariff(service_kind="repair", selector_label="Диагностика",
                           estimate_template="Диагностика", short_name="Диагностика",
                           base_price=100)
    db.add_all([storefront, source])
    await db.commit()
    manifest = PartnerSiteSetupManifest(tenant_slug=tenant.slug, storefront_slug="main",
                                       site={"display_name": "Test 1"}, enabled_services=["repair"])
    return manifest, source, tenant.id


@pytest.mark.asyncio
async def test_setup_is_reviewed_atomic_and_does_not_overwrite_partner_data(db):
    manifest, source, tenant_id = await seed(db)
    report, scope = await PartnerSiteSetupService.plan(db, manifest)
    assert report["blockers"] == []
    assert (await db.execute(select(StorefrontSettings))).first() is None
    token = PartnerSiteSetupPlanToken.issue(plan_digest=report["plan_digest"])
    await db.rollback()
    async with db.begin():
        result = await PartnerSiteSetupService.execute(db, manifest, plan_token=token)
        assert result["settings_version"] == 1
    copied = (await db.execute(select(ServiceTariff).where(ServiceTariff.tenant_id == tenant_id))).scalar_one()
    assert copied.base_price == 100
    copied_id = copied.id
    copied.base_price = 230
    await db.commit()
    report, _ = await PartnerSiteSetupService.plan(db, manifest)
    assert len(report["blockers"]) == 2
    replay = PartnerSiteSetupPlanToken.issue(plan_digest=report["plan_digest"])
    with pytest.raises(StorefrontOnboardingBlockedError):
        await PartnerSiteSetupService.execute(db, manifest, plan_token=replay)
    await db.rollback()
    assert (await db.get(ServiceTariff, copied_id)).base_price == 230


@pytest.mark.asyncio
async def test_setup_rejects_changed_source_after_review(db):
    manifest, source, tenant_id = await seed(db)
    report, _ = await PartnerSiteSetupService.plan(db, manifest)
    token = PartnerSiteSetupPlanToken.issue(plan_digest=report["plan_digest"])
    source.base_price = 150
    await db.commit()
    with pytest.raises(StorefrontOnboardingBlockedError, match="State changed"):
        await PartnerSiteSetupService.execute(db, manifest, plan_token=token)
    await db.rollback()
    assert (await db.execute(select(ServiceTariff).where(ServiceTariff.tenant_id == tenant_id))).first() is None
    assert (await db.execute(select(StorefrontSettings))).first() is None
