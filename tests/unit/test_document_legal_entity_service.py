from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models import DocumentLegalEntity, Tenant
from models.tenancy import TenantScope
from modules.documents.application.legal_entities import (
    DocumentLegalEntityError,
    DocumentLegalEntityService,
)
from routers import manager_operation_ids as operation_ids
from routers.manager_permission_policy import STOREFRONT_OWNER_OPERATION_IDS


@pytest.mark.asyncio
async def test_legal_entities_are_tenant_scoped_and_first_one_becomes_default(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'entities.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Tenant.__table__.create)
        await connection.run_sync(DocumentLegalEntity.__table__.create)

    try:
        async with sessions() as session:
            first_tenant = Tenant(slug="first", display_name="First")
            second_tenant = Tenant(slug="second", display_name="Second")
            session.add_all([first_tenant, second_tenant])
            await session.commit()
            await session.refresh(first_tenant)
            await session.refresh(second_tenant)

            first_scope = TenantScope(int(first_tenant.id), 1)
            second_scope = TenantScope(int(second_tenant.id), 2)
            first = await DocumentLegalEntityService.create(
                session,
                tenant_scope=first_scope,
                display_name="ООО Первый",
                slug=None,
                legal_name="Общество с ограниченной ответственностью Первый",
                unp="100000001",
                is_vat_payer=False,
                is_default=False,
                requisites={"iban": "BY00TEST"},
            )
            await DocumentLegalEntityService.create(
                session,
                tenant_scope=second_scope,
                display_name="ООО Второй",
                slug="second-issuer",
                legal_name=None,
                unp=None,
                is_vat_payer=False,
                is_default=False,
                requisites={},
            )

            assert first.is_default is True
            assert [
                row.display_name
                for row in await DocumentLegalEntityService.list(
                    session,
                    tenant_scope=first_scope,
                )
            ] == ["ООО Первый"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_switching_default_is_atomic_and_default_cannot_be_disabled(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'defaults.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Tenant.__table__.create)
        await connection.run_sync(DocumentLegalEntity.__table__.create)

    try:
        async with sessions() as session:
            tenant = Tenant(slug="mvn", display_name="MVN")
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)
            scope = TenantScope(int(tenant.id), 1)
            first = await DocumentLegalEntityService.create(
                session,
                tenant_scope=scope,
                display_name="ИП Первый",
                slug="first",
                legal_name=None,
                unp=None,
                is_vat_payer=False,
                is_default=True,
                requisites={},
            )
            second = await DocumentLegalEntityService.create(
                session,
                tenant_scope=scope,
                display_name="ООО Второй",
                slug="second",
                legal_name=None,
                unp=None,
                is_vat_payer=True,
                is_default=False,
                requisites={},
            )

            second = await DocumentLegalEntityService.update(
                session,
                tenant_scope=scope,
                legal_entity_id=int(second.id),
                changes={"is_default": True},
            )
            rows = await DocumentLegalEntityService.list(session, tenant_scope=scope)
            assert second.is_default is True
            assert sum(row.is_default for row in rows) == 1
            assert next(row for row in rows if row.id == first.id).is_default is False

            with pytest.raises(DocumentLegalEntityError, match="Нельзя отключить"):
                await DocumentLegalEntityService.update(
                    session,
                    tenant_scope=scope,
                    legal_entity_id=int(second.id),
                    changes={"status": "disabled"},
                )
    finally:
        await engine.dispose()


def test_legal_entity_mutations_require_tenant_owner_permission() -> None:
    assert (
        operation_ids.CREATE_MANAGER_DOCUMENT_LEGAL_ENTITY
        in STOREFRONT_OWNER_OPERATION_IDS
    )
    assert (
        operation_ids.PATCH_MANAGER_DOCUMENT_LEGAL_ENTITY
        in STOREFRONT_OWNER_OPERATION_IDS
    )
    assert (
        operation_ids.DOWNLOAD_MANAGER_NATIVE_TEMPLATE_VERSION_SOURCE
        in STOREFRONT_OWNER_OPERATION_IDS
    )
