"""Install an issuer's initial native form once, preserving configured templates."""

import asyncio
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import DocumentLegalEntity, DocumentTemplate, DocumentTemplateVersion
from models.tenancy import TenantScope
from modules.documents.infrastructure.template_source_storage import TemplateSourceStorage
from .errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from .template_versions import NativeTemplatePlaceholderContract


async def check_initial_template_available(
    session: AsyncSession, *, scope: TenantScope, legal_entity_id: int, document_type: str, name: str | None = None,
) -> None:
    configured = select(DocumentTemplate.id).where(
        DocumentTemplate.tenant_id == scope.tenant_id, DocumentTemplate.legal_entity_id == legal_entity_id,
        DocumentTemplate.doc_type == document_type,
    )
    if name is not None:
        configured = configured.where(DocumentTemplate.name == name)
    if await session.scalar(configured.limit(1)) is not None:
        raise ManagedDocumentConflictError(
            "Начальный шаблон отключён или не имеет активной версии. Проверьте настройки документов."
        )


async def ensure_initial_template(
    session: AsyncSession, *, scope: TenantScope, legal_entity_id: int, storage: TemplateSourceStorage | None,
    document_type: str, name: str, filename: str, description: str,
    content_factory: Callable[[], bytes], placeholder_contract: NativeTemplatePlaceholderContract,
    allow_alongside_custom: bool = False,
) -> None:
    issuer_id = await session.scalar(select(DocumentLegalEntity.id).where(
        DocumentLegalEntity.id == legal_entity_id, DocumentLegalEntity.tenant_id == scope.tenant_id,
        DocumentLegalEntity.status == "active",
    ).with_for_update())
    if issuer_id is None:
        raise ManagedDocumentNotFoundError("Активное юридическое лицо не найдено")
    templates = select(DocumentTemplate.id).where(
        DocumentTemplate.tenant_id == scope.tenant_id,
        DocumentTemplate.legal_entity_id == issuer_id,
        DocumentTemplate.doc_type == document_type,
    )
    active = await session.scalar(templates.join(
        DocumentTemplateVersion, DocumentTemplateVersion.template_id == DocumentTemplate.id,
    ).where(DocumentTemplate.is_active.is_(True), DocumentTemplateVersion.status == "active",
            DocumentTemplateVersion.renderer == "docx").limit(1))
    if active is not None:
        return
    await check_initial_template_available(
        session, scope=scope, legal_entity_id=issuer_id, document_type=document_type,
        name=name if allow_alongside_custom else None,
    )
    if storage is None:
        raise ManagedDocumentConflictError("Для начального шаблона требуется хранилище документов")

    content = await asyncio.to_thread(content_factory)
    template = DocumentTemplate(tenant_id=scope.tenant_id, legal_entity_id=issuer_id,
                                name=name, doc_type=document_type, is_default=True, description=description)
    session.add(template)
    await session.flush()
    source = await storage.save(tenant_id=scope.tenant_id, template_id=template.id, version=1,
                                filename=filename, content=content)
    session.add(DocumentTemplateVersion(template_id=template.id, version=1, status="active", renderer="docx",
        source_storage_key=source.storage_key, source_filename=source.filename,
        checksum_sha256=source.checksum_sha256, placeholder_schema=placeholder_contract.as_persisted_schema(),
        change_note="Начальная редактируемая форма"))
    await session.flush()
