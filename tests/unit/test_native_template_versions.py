from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from docx import Document
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models import (
    Customer,
    DocumentLegalEntity,
    DocumentTemplate,
    DocumentTemplateActLink,
    DocumentTemplateCustomerLink,
    DocumentTemplateVersion,
    Tenant,
)
from models.tenancy import TenantScope
from modules.documents.application.template_versions import (
    NativeTemplatePlaceholderContract,
    NativeTemplateVersionService,
    TemplateVersionError,
    TemplateVersionNotFoundError,
    TemplateVersionValidationError,
)
from modules.documents.infrastructure.renderers import TableBlockSpec
from modules.documents.infrastructure.template_source_storage import (
    PrivateTemplateSourceStorage,
    StoredTemplateSource,
)
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from sqlmodel import select


def _docx_bytes(*, placeholder: str = "document.official_number") -> bytes:
    document = Document()
    document.add_paragraph(f"Документ № {{{{ {placeholder} }}}}")
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _contract() -> NativeTemplatePlaceholderContract:
    return NativeTemplatePlaceholderContract.create(
        field_catalog={"document.official_number"},
        table_blocks=(),
    )


async def _database(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'templates.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        for model in (
            Tenant,
            DocumentLegalEntity,
            Customer,
            DocumentTemplate,
            DocumentTemplateCustomerLink,
            DocumentTemplateActLink,
            DocumentTemplateVersion,
        ):
            await connection.run_sync(model.__table__.create)
    return engine, sessions


async def _scopes_and_issuers(session):
    first_tenant = Tenant(slug="first", display_name="First")
    second_tenant = Tenant(slug="second", display_name="Second")
    session.add_all([first_tenant, second_tenant])
    await session.commit()
    await session.refresh(first_tenant)
    await session.refresh(second_tenant)
    first_issuer = DocumentLegalEntity(
        tenant_id=first_tenant.id,
        slug="first-issuer",
        display_name="First issuer",
        requisites={},
    )
    second_issuer = DocumentLegalEntity(
        tenant_id=second_tenant.id,
        slug="second-issuer",
        display_name="Second issuer",
        requisites={},
    )
    session.add_all([first_issuer, second_issuer])
    await session.commit()
    await session.refresh(first_issuer)
    await session.refresh(second_issuer)
    return (
        TenantScope(int(first_tenant.id), 1),
        TenantScope(int(second_tenant.id), 2),
        first_issuer,
        second_issuer,
    )


@pytest.mark.asyncio
async def test_native_templates_are_tenant_and_legal_entity_scoped(
    tmp_path: Path,
) -> None:
    engine, sessions = await _database(tmp_path)
    try:
        async with sessions() as session:
            (
                first_scope,
                second_scope,
                first_issuer,
                second_issuer,
            ) = await _scopes_and_issuers(session)
            template = await NativeTemplateVersionService.create_template(
                session,
                tenant_scope=first_scope,
                legal_entity_id=int(first_issuer.id),
                name="Договор",
                doc_type="contract",
            )

            with pytest.raises(TemplateVersionNotFoundError):
                await NativeTemplateVersionService.list_versions(
                    session,
                    tenant_scope=second_scope,
                    legal_entity_id=int(second_issuer.id),
                    template_id=int(template.id),
                )

            assert template.tenant_id == first_scope.tenant_id
            assert template.legal_entity_id == first_issuer.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_uploads_increment_versions_and_private_source_readback_is_verified(
    tmp_path: Path,
) -> None:
    engine, sessions = await _database(tmp_path)
    storage = PrivateTemplateSourceStorage(
        LocalPrivateAttachmentStorage(tmp_path / "private")
    )
    first_content = _docx_bytes()
    second_content = _docx_bytes()
    try:
        async with sessions() as session:
            scope, _, issuer, _ = await _scopes_and_issuers(session)
            template = await NativeTemplateVersionService.create_template(
                session,
                tenant_scope=scope,
                legal_entity_id=int(issuer.id),
                name="Счёт",
                doc_type="invoice",
            )
            first = await NativeTemplateVersionService.upload_native_docx_version(
                session,
                tenant_scope=scope,
                legal_entity_id=int(issuer.id),
                template_id=int(template.id),
                filename="Счёт.docx",
                content=first_content,
                placeholder_contract=_contract(),
                storage=storage,
                change_note="Первая редакция",
            )
            second = await NativeTemplateVersionService.upload_native_docx_version(
                session,
                tenant_scope=scope,
                legal_entity_id=int(issuer.id),
                template_id=int(template.id),
                filename="Счёт.docx",
                content=second_content,
                placeholder_contract=_contract(),
                storage=storage,
            )

            assert (first.version, second.version) == (1, 2)
            assert first.status == second.status == "draft"
            assert second.placeholder_schema == {
                "fields": ["document.official_number"],
                "tables": [],
            }
            assert (
                await storage.read(
                    StoredTemplateSource(
                        tenant_id=scope.tenant_id,
                        template_id=int(template.id),
                        version=first.version,
                        provider=storage.provider_name,
                        storage_key=first.source_storage_key,
                        filename=str(first.source_filename),
                        checksum_sha256=first.checksum_sha256,
                        size_bytes=len(first_content),
                    )
                )
                == first_content
            )
            assert (
                await storage.read_persisted(
                    tenant_id=scope.tenant_id,
                    template_id=int(template.id),
                    version=first.version,
                    storage_key=first.source_storage_key,
                    filename=str(first.source_filename),
                    checksum_sha256=first.checksum_sha256,
                )
                == first_content
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unknown_placeholder_does_not_persist_a_version_or_source(
    tmp_path: Path,
) -> None:
    engine, sessions = await _database(tmp_path)
    private_root = tmp_path / "private"
    storage = PrivateTemplateSourceStorage(LocalPrivateAttachmentStorage(private_root))
    try:
        async with sessions() as session:
            scope, _, issuer, _ = await _scopes_and_issuers(session)
            template = await NativeTemplateVersionService.create_template(
                session,
                tenant_scope=scope,
                legal_entity_id=int(issuer.id),
                name="Акт",
                doc_type="act",
            )
            with pytest.raises(
                TemplateVersionValidationError, match="not in this template"
            ):
                await NativeTemplateVersionService.upload_native_docx_version(
                    session,
                    tenant_scope=scope,
                    legal_entity_id=int(issuer.id),
                    template_id=int(template.id),
                    filename="Акт.docx",
                    content=_docx_bytes(placeholder="internal.secret"),
                    placeholder_contract=_contract(),
                    storage=storage,
                )

            rows = (
                (await session.execute(select(DocumentTemplateVersion))).scalars().all()
            )
            assert rows == []
            assert not private_root.exists()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_activation_retires_previous_version_and_leaves_exactly_one_active(
    tmp_path: Path,
) -> None:
    engine, sessions = await _database(tmp_path)
    storage = PrivateTemplateSourceStorage(
        LocalPrivateAttachmentStorage(tmp_path / "private")
    )
    try:
        async with sessions() as session:
            scope, _, issuer, _ = await _scopes_and_issuers(session)
            template = await NativeTemplateVersionService.create_template(
                session,
                tenant_scope=scope,
                legal_entity_id=int(issuer.id),
                name="КП",
                doc_type="commercial_offer",
            )
            first = await NativeTemplateVersionService.upload_native_docx_version(
                session,
                tenant_scope=scope,
                legal_entity_id=int(issuer.id),
                template_id=int(template.id),
                filename="КП.docx",
                content=_docx_bytes(),
                placeholder_contract=_contract(),
                storage=storage,
            )
            second = await NativeTemplateVersionService.upload_native_docx_version(
                session,
                tenant_scope=scope,
                legal_entity_id=int(issuer.id),
                template_id=int(template.id),
                filename="КП.docx",
                content=_docx_bytes(placeholder="document.official_number"),
                placeholder_contract=_contract(),
                storage=storage,
            )
            await NativeTemplateVersionService.activate_version(
                session,
                tenant_scope=scope,
                legal_entity_id=int(issuer.id),
                template_id=int(template.id),
                version_id=int(first.id),
            )
            activated = await NativeTemplateVersionService.activate_version(
                session,
                tenant_scope=scope,
                legal_entity_id=int(issuer.id),
                template_id=int(template.id),
                version_id=int(second.id),
            )

            versions = await NativeTemplateVersionService.list_versions(
                session,
                tenant_scope=scope,
                legal_entity_id=int(issuer.id),
                template_id=int(template.id),
            )
            assert activated.status == "active"
            assert [(row.version, row.status) for row in versions] == [
                (2, "active"),
                (1, "retired"),
            ]
            assert sum(row.status == "active" for row in versions) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_malicious_docx_zip_is_rejected_before_storage_or_persistence(
    tmp_path: Path,
) -> None:
    engine, sessions = await _database(tmp_path)
    private_root = tmp_path / "private"
    storage = PrivateTemplateSourceStorage(LocalPrivateAttachmentStorage(private_root))
    payload = BytesIO()
    with ZipFile(payload, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<types />")
        archive.writestr("word/document.xml", "<document />")
        archive.writestr("../escape.txt", "no")
    try:
        async with sessions() as session:
            scope, _, issuer, _ = await _scopes_and_issuers(session)
            template = await NativeTemplateVersionService.create_template(
                session,
                tenant_scope=scope,
                legal_entity_id=int(issuer.id),
                name="Накладная",
                doc_type="waybill",
            )
            with pytest.raises(TemplateVersionError, match="небезопасный путь"):
                await NativeTemplateVersionService.upload_native_docx_version(
                    session,
                    tenant_scope=scope,
                    legal_entity_id=int(issuer.id),
                    template_id=int(template.id),
                    filename="Накладная.docx",
                    content=payload.getvalue(),
                    placeholder_contract=_contract(),
                    storage=storage,
                )
            assert (
                await session.execute(select(DocumentTemplateVersion))
            ).scalars().all() == []
            assert not private_root.exists()
    finally:
        await engine.dispose()


def test_contract_rejects_unsafe_fields_and_mixed_table_blocks() -> None:
    with pytest.raises(TemplateVersionError, match="недопустимое имя"):
        NativeTemplatePlaceholderContract.create(field_catalog={"customer.__class__"})
    with pytest.raises(TemplateVersionError, match="принадлежать только одному"):
        NativeTemplatePlaceholderContract.create(
            field_catalog=(),
            table_blocks=(
                TableBlockSpec(name="lines", row_fields=frozenset({"line.title"})),
                TableBlockSpec(name="extras", row_fields=frozenset({"line.title"})),
            ),
        )
