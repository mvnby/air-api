"""New partners get the approved book once, then own their edits."""

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import models  # noqa: F401 - register tables
from models import InstallationPriceBook, ServiceTariff, ServiceTariffRule, Storefront, Tenant
from models.tenancy import TenantScope
from services.installation_grid_seed import canonical_installation_grid
from services.installation_price_book_service import InstallationPriceBookService
from services.service_catalog_template_service import ServiceCatalogTemplateService


@pytest.mark.asyncio
async def test_initial_partner_copy_publishes_only_current_approved_source():
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
                spec = canonical_installation_grid()[0]
                source = ServiceTariff(**spec.fields())
                session.add_all([
                    Storefront(tenant_id=system.id, slug="main", display_name="MVN",
                               status="active", is_default=True),
                    Storefront(tenant_id=partner.id, slug="main", display_name="Partner",
                               status="active", is_default=True),
                    ServiceTariff(service_kind="installation", selector_label="История",
                                  installation_code="installation.old", is_active=False,
                                  installation_match={"indoor_type": "wall"}, base_price=500),
                    source,
                ])
                await session.flush()
                session.add_all(ServiceTariffRule(
                    tariff_id=source.id, sort_order=index * 10, **rule.fields(),
                ) for index, rule in enumerate(spec.rules))
                await session.flush()
                system_storefront = (await session.execute(select(Storefront).where(
                    Storefront.tenant_id == system.id,
                ))).scalar_one()
                await InstallationPriceBookService.publish(
                    session, TenantScope(tenant_id=system.id,
                                         storefront_id=system_storefront.id,
                                         is_system=True),
                    actor="test:approved-source", commit=False,
                )
            target_storefront = (await session.execute(select(Storefront).where(
                Storefront.tenant_id == partner.id))).scalar_one()
            target = TenantScope(tenant_id=partner.id, storefront_id=target_storefront.id)

            preview = await ServiceCatalogTemplateService.preview(session, tenant_scope=target)
            assert preview.source_counts.tariffs == 1  # inactive historical draft excluded
            await ServiceCatalogTemplateService.clone(
                session, tenant_scope=target,
                expected_fingerprint=preview.source_fingerprint,
            )
            copied = (await session.execute(select(ServiceTariff).where(
                ServiceTariff.tenant_id == partner.id))).scalar_one()
            assert copied.installation_code == spec.code
            assert copied.base_price == 600
            partner_book = (await session.execute(select(InstallationPriceBook).where(
                InstallationPriceBook.tenant_id == partner.id))).scalar_one()
            assert partner_book.revision == 1
            assert partner_book.entries[0]["base_price"] == "600.00"
            copied.base_price = 700
            await session.commit()
            canonical = (await session.execute(select(ServiceTariff).where(
                ServiceTariff.tenant_id.is_(None), ServiceTariff.is_active.is_(True)))).scalar_one()
            assert canonical.base_price == 600
            canonical.base_price = 650
            await session.commit()

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
            pending_preview = await ServiceCatalogTemplateService.preview(
                session, tenant_scope=another_scope,
            )
            assert pending_preview.can_clone is False
            with pytest.raises(HTTPException) as exc:
                await ServiceCatalogTemplateService.clone(
                    session, tenant_scope=another_scope,
                    expected_fingerprint=pending_preview.source_fingerprint,
                )
            assert exc.value.status_code == 409
            await session.rollback()
            assert (await session.execute(select(ServiceTariff).where(
                ServiceTariff.tenant_id == another_id))).first() is None
    finally:
        await engine.dispose()
