"""Revision increments must refresh rows retained across transactions."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from crud.catalog_revision import CATALOG_REVISION_KEY, CatalogRevisionDAO
from models import GlobalConfig, Storefront, StorefrontCatalogRevision, Tenant
from models.tenancy import TenantScope


@pytest.mark.asyncio
@pytest.mark.parametrize("scoped", [False, True])
async def test_revision_bump_refreshes_retained_orm_snapshot(scoped):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    scope = TenantScope(tenant_id=1, storefront_id=1)

    async def bump(session):
        if scoped:
            return await CatalogRevisionDAO.bump_storefront(session, tenant_scope=scope)
        return await CatalogRevisionDAO.bump(session, scope="retained_revision_test")

    try:
        async with factory() as setup:
            setup.add(Tenant(id=1, slug="revision-test", display_name="Test"))
            await setup.flush()
            setup.add(Storefront(id=1, tenant_id=1, slug="main", display_name="Test"))
            await setup.flush()
            if scoped:
                setup.add(StorefrontCatalogRevision(tenant_id=1, storefront_id=1, revision=4))
            else:
                setup.add(GlobalConfig(key=CATALOG_REVISION_KEY, value="4"))
            await setup.commit()

        async with factory() as retained, factory() as concurrent:
            if scoped:
                original = await retained.get(StorefrontCatalogRevision, (1, 1))
            else:
                original = (await retained.execute(select(GlobalConfig).where(
                    GlobalConfig.key == CATALOG_REVISION_KEY,
                ))).scalar_one()
            await retained.commit()

            assert (await bump(concurrent)).revision == 5
            await concurrent.commit()
            assert (original.revision if scoped else int(original.value)) == 4

            assert (await bump(retained)).revision == 6
            await retained.commit()
            assert (original.revision if scoped else int(original.value)) == 6

        async with factory() as verification:
            current = (
                await CatalogRevisionDAO.get_storefront_current(verification, tenant_scope=scope)
                if scoped else await CatalogRevisionDAO.get_current(verification)
            )
            assert current.revision == 6
    finally:
        await engine.dispose()
