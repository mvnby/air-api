"""A reviewed grid reset cannot lose tenant edits or rewrite history."""

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import models  # noqa: F401 - register all SQLModel tables for isolated SQLite tests
from models import (
    InstallationPriceBook, InstallationRate, ServiceTariff, ServiceTariffRule,
    Storefront, Tenant, TenantAuditEvent,
)
from services.installation_grid_rollout import (
    InstallationGridPlanToken, InstallationGridRolloutService,
)
from services.storefront_onboarding_state import StorefrontOnboardingBlockedError


@pytest.fixture
async def grid_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        async with session.begin():
            system = Tenant(slug="mvn", display_name="MVN", is_system=True)
            partner = Tenant(slug="test1", display_name="Test 1", demo_read_only=True)
            session.add_all([system, partner])
            await session.flush()
            session.add_all([
                Storefront(tenant_id=system.id, slug="main", display_name="MVN",
                           status="active", is_default=True),
                Storefront(tenant_id=partner.id, slug="main", display_name="Test 1",
                           status="active", is_default=True),
                ServiceTariff(service_kind="installation", selector_label="Старый монтаж",
                              category="Wall", power_range="07,09,12", base_price=500,
                              installation_match={"indoor_type": "wall"},
                              installation_code="installation.old", is_active=True),
                ServiceTariff(tenant_id=partner.id, service_kind="installation",
                              selector_label="Партнёрский старый монтаж", category="Wall",
                              power_range="07,09,12", base_price=515,
                              installation_match={"indoor_type": "wall"},
                              installation_code="installation.old", is_active=True),
                ServiceTariff(tenant_id=partner.id, service_kind="repair",
                              selector_label="Ремонт", base_price=150, is_active=True),
                InstallationRate(category="Wall", power_range="07,09,12",
                                 base_price=500, extra_pipe_price=40,
                                 included_pipe_meters=3, is_fixed=True),
                InstallationPriceBook(tenant_id=partner.id, revision=1,
                                      fingerprint="historical", entries=[]),
            ])
        yield session
    await engine.dispose()


PROOFS = dict(
    expected_partner_slugs=("test1",),
    backend_release_commit="b" * 40,
    backend_image_digest="sha256:" + "c" * 64,
    web_v2_commit="a" * 40,
    web_v2_proof="https://github.com/mvnby/mvn-web/actions/runs/1",
    manager_editor_proof="https://github.com/mvnby/air-api/actions/runs/2",
    legacy_list_proof="https://github.com/mvnby/air-api/actions/runs/5",
    legacy_calculate_proof="https://github.com/mvnby/air-api/actions/runs/3",
    legacy_tariff_calculate_proof="https://github.com/mvnby/air-api/actions/runs/4",
    include_demo_reset=True,
)


@pytest.mark.asyncio
async def test_plan_reports_exact_old_new_prices_and_never_writes(grid_db, monkeypatch):
    monkeypatch.setattr("services.installation_grid_rollout._validate_seed_against_installed_contract",
                        lambda: None)
    report, _ = await InstallationGridRolloutService.plan(grid_db, **PROOFS)
    assert report["blockers"] == []
    assert report["discovered_active_partner_slugs"] == ["test1"]
    assert len(report["desired_installation_drafts"]) == 20
    partner = next(row for row in report["scopes"] if row["tenant_slug"] == "test1")
    assert partner["demo_read_only"] is True
    assert partner["old_to_new"][0]["old_base_price"] == 515
    assert partner["old_to_new"][0]["price_comparison"]["new_candidates"][0]["new_base_price"] == 600
    assert partner["latest_book"]["fingerprint"] == "historical"
    assert (await grid_db.execute(select(ServiceTariff).where(
        ServiceTariff.service_kind == "installation"))).scalars().all()
    assert len((await grid_db.execute(select(TenantAuditEvent))).scalars().all()) == 0
    await grid_db.rollback()

    blocked, _ = await InstallationGridRolloutService.plan(
        grid_db, **{**PROOFS, "include_demo_reset": False},
    )
    assert "explicit_include_demo_reset_required" in blocked["blockers"]
    await grid_db.rollback()


@pytest.mark.asyncio
async def test_stale_plan_blocks_and_fresh_plan_retains_old_rows_and_book(grid_db, monkeypatch):
    monkeypatch.setattr("services.installation_grid_rollout._validate_seed_against_installed_contract",
                        lambda: None)

    async def publish(session, scope, *, actor, commit):
        assert commit is False
        previous = (await session.execute(select(InstallationPriceBook).where(
            InstallationPriceBook.tenant_id == scope.tenant_id,
        ).order_by(InstallationPriceBook.revision.desc()))).scalars().first()
        book = InstallationPriceBook(
            tenant_id=scope.tenant_id,
            revision=previous.revision + 1 if previous else 1,
            fingerprint=f"new-{scope.tenant_id}", entries=[], published_by=actor,
        )
        session.add(book)
        await session.flush()
        return SimpleNamespace(price_book_id=book.id, revision=book.revision,
                               fingerprint=book.fingerprint)

    monkeypatch.setattr("services.installation_grid_rollout.InstallationPriceBookService.publish",
                        publish)
    report, _ = await InstallationGridRolloutService.plan(grid_db, **PROOFS)
    stale_token = InstallationGridPlanToken.issue(plan_digest=report["plan_digest"])
    await grid_db.rollback()
    partner_old = (await grid_db.execute(select(ServiceTariff).where(
        ServiceTariff.tenant_id.is_not(None),
        ServiceTariff.service_kind == "installation"))).scalar_one()
    partner_old_id = partner_old.id
    partner_tenant_id = partner_old.tenant_id
    partner_old.base_price = 520
    await grid_db.commit()
    with pytest.raises(StorefrontOnboardingBlockedError, match="State changed"):
        await InstallationGridRolloutService.apply(
            grid_db, **PROOFS, plan_token=stale_token,
        )
    await grid_db.rollback()
    assert (await grid_db.get(ServiceTariff, partner_old_id)).is_active is True

    fresh, _ = await InstallationGridRolloutService.plan(grid_db, **PROOFS)
    token = InstallationGridPlanToken.issue(plan_digest=fresh["plan_digest"])
    await grid_db.rollback()
    async with grid_db.begin():
        result = await InstallationGridRolloutService.apply(
            grid_db, **PROOFS, plan_token=token,
        )
        assert result["status"] == "applied"
        assert len(result["scopes"]) == 2
    assert (await grid_db.get(ServiceTariff, partner_old_id)).is_active is False
    partner_active = list((await grid_db.execute(select(ServiceTariff).where(
        ServiceTariff.tenant_id == partner_tenant_id,
        ServiceTariff.service_kind == "installation",
        ServiceTariff.is_active.is_(True)))).scalars().all())
    assert len(partner_active) == 20
    assert all(row.source_tariff_id is not None for row in partner_active)
    assert (await grid_db.execute(select(ServiceTariff).where(
        ServiceTariff.tenant_id == partner_tenant_id,
        ServiceTariff.service_kind == "repair"))).scalar_one().base_price == 150
    books = list((await grid_db.execute(select(InstallationPriceBook).where(
        InstallationPriceBook.tenant_id == partner_tenant_id,
    ).order_by(InstallationPriceBook.revision))).scalars().all())
    assert [(book.revision, book.fingerprint) for book in books] == [
        (1, "historical"), (2, f"new-{partner_tenant_id}"),
    ]
    audits = list((await grid_db.execute(select(TenantAuditEvent))).scalars().all())
    assert len(audits) == 2
    partner_audit = next(row for row in audits if row.tenant_id == partner_tenant_id)
    assert partner_audit.change_set["before_installation_drafts"][0]["base_price"] == 520
    await grid_db.rollback()


@pytest.mark.asyncio
async def test_failure_during_partner_publication_rolls_back_every_scope(grid_db, monkeypatch):
    monkeypatch.setattr("services.installation_grid_rollout._validate_seed_against_installed_contract",
                        lambda: None)
    report, _ = await InstallationGridRolloutService.plan(grid_db, **PROOFS)
    token = InstallationGridPlanToken.issue(plan_digest=report["plan_digest"])
    await grid_db.rollback()

    async def fail_partner_publish(session, scope, *, actor, commit):
        assert commit is False
        if not scope.is_system:
            raise RuntimeError("partner publication failed")
        book = InstallationPriceBook(tenant_id=scope.tenant_id, revision=1,
                                     fingerprint="uncommitted", entries=[])
        session.add(book)
        await session.flush()
        return SimpleNamespace(price_book_id=book.id, revision=1,
                               fingerprint="uncommitted")

    monkeypatch.setattr("services.installation_grid_rollout.InstallationPriceBookService.publish",
                        fail_partner_publish)
    with pytest.raises(RuntimeError, match="partner publication failed"):
        async with grid_db.begin():
            await InstallationGridRolloutService.apply(
                grid_db, **PROOFS, plan_token=token,
            )
    originals = list((await grid_db.execute(select(ServiceTariff).where(
        ServiceTariff.service_kind == "installation",
    ))).scalars().all())
    assert len(originals) == 2
    assert all(row.is_active for row in originals)
    assert not any("v20260925" in (row.installation_code or "") for row in originals)
    assert len((await grid_db.execute(select(TenantAuditEvent))).scalars().all()) == 0
    books = list((await grid_db.execute(select(InstallationPriceBook))).scalars().all())
    assert [(book.revision, book.fingerprint) for book in books] == [(1, "historical")]
    await grid_db.rollback()
