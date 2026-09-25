"""New partners get the approved book once, then own their edits."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import models  # noqa: F401 - register tables
from models import InstallationPriceBook, ServiceTariff, Storefront, Tenant
from models.tenancy import TenantScope
from services.service_catalog_template_service import ServiceCatalogTemplateService


@pytest.mark.asyncio
async def test_initial_partner_copy_publishes_only_current_approved_source(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            async with session.begin():
                system = Tenant(slug="mvn", display_name="MVN", is_system=True)
                partner = Tenant(slug="partner", display_name="Partner")
                session.add_all([system, partner])
                await session.flush()
                session.add_all([
                    Storefront(tenant_id=system.id, slug="main", display_name="MVN",
                               status="active", is_default=True),
                    Storefront(tenant_id=partner.id, slug="main", display_name="Partner",
                               status="active", is_default=True),
                    ServiceTariff(service_kind="installation", selector_label="История",
                                  installation_code="installation.old", is_active=False,
                                  installation_match={"indoor_type": "wall"}, base_price=500),
                    ServiceTariff(service_kind="installation", selector_label="Новый монтаж",
                                  installation_code="installation.new", is_active=True,
                                  installation_match={"indoor_type": "wall"}, base_price=600),
                    InstallationPriceBook(tenant_id=system.id, revision=2,
                                          fingerprint="approved", entries=[]),
                ])
            target_storefront = (await session.execute(select(Storefront).where(
                Storefront.tenant_id == partner.id))).scalar_one()
            target = TenantScope(tenant_id=partner.id, storefront_id=target_storefront.id)

            async def current_fingerprint(_session, _scope):
                return "approved"

            async def publish(_session, scope, *, actor, commit):
                assert commit is False and scope.tenant_id == partner.id
                book = InstallationPriceBook(tenant_id=scope.tenant_id, revision=1,
                                             fingerprint="partner-own-book", entries=[],
                                             published_by=actor)
                _session.add(book)
                await _session.flush()
                return SimpleNamespace(revision=book.revision)

            monkeypatch.setattr(
                "services.service_catalog_template_service.InstallationPriceBookService.current_draft_fingerprint",
                current_fingerprint,
                raising=False,
            )
            monkeypatch.setattr(
                "services.service_catalog_template_service.InstallationPriceBookService.publish",
                publish,
            )
            preview = await ServiceCatalogTemplateService.preview(session, tenant_scope=target)
            assert preview.source_counts.tariffs == 1  # inactive historical draft excluded
            await ServiceCatalogTemplateService.clone(
                session, tenant_scope=target,
                expected_fingerprint=preview.source_fingerprint,
            )
            copied = (await session.execute(select(ServiceTariff).where(
                ServiceTariff.tenant_id == partner.id))).scalar_one()
            assert copied.installation_code == "installation.new"
            assert copied.base_price == 600
            assert (await session.execute(select(InstallationPriceBook).where(
                InstallationPriceBook.tenant_id == partner.id))).scalar_one().fingerprint == "partner-own-book"
            copied.base_price = 700
            await session.commit()
            canonical = (await session.execute(select(ServiceTariff).where(
                ServiceTariff.tenant_id.is_(None), ServiceTariff.is_active.is_(True)))).scalar_one()
            assert canonical.base_price == 600

            another = Tenant(slug="another", display_name="Another")
            session.add(another)
            await session.flush()
            another_id = another.id
            another_storefront = Storefront(tenant_id=another.id, slug="main",
                                            display_name="Another", status="active",
                                            is_default=True)
            session.add(another_storefront)
            await session.commit()
            another_scope = TenantScope(tenant_id=another.id,
                                        storefront_id=another_storefront.id)
            another_preview = await ServiceCatalogTemplateService.preview(
                session, tenant_scope=another_scope,
            )

            async def pending_fingerprint(_session, _scope):
                return "pending-unpublished-change"

            monkeypatch.setattr(
                "services.service_catalog_template_service.InstallationPriceBookService.current_draft_fingerprint",
                pending_fingerprint,
                raising=False,
            )
            pending_preview = await ServiceCatalogTemplateService.preview(
                session, tenant_scope=another_scope,
            )
            assert pending_preview.can_clone is False
            with pytest.raises(HTTPException) as exc:
                await ServiceCatalogTemplateService.clone(
                    session, tenant_scope=another_scope,
                    expected_fingerprint=another_preview.source_fingerprint,
                )
            assert exc.value.status_code == 409
            await session.rollback()
            assert (await session.execute(select(ServiceTariff).where(
                ServiceTariff.tenant_id == another_id))).first() is None
    finally:
        await engine.dispose()
