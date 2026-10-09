"""Install the initial native form at first use, respecting disabled/custom forms."""
import asyncio

from sqlmodel import select

from models import DocumentLegalEntity, DocumentTemplate, DocumentTemplateVersion
from modules.documents.infrastructure.renderers.participant_statement_template import TYPE, NAME, FIELDS, template_bytes
from .errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from .template_versions import NativeTemplatePlaceholderContract


async def ensure_initial_participant_template(session, *, scope, legal_entity_id, storage):
    issuer = await session.scalar(select(DocumentLegalEntity).where(
        DocumentLegalEntity.id == legal_entity_id,
        DocumentLegalEntity.tenant_id == scope.tenant_id,
        DocumentLegalEntity.status == "active",
    ).with_for_update())
    if issuer is None:
        raise ManagedDocumentNotFoundError("Активное юридическое лицо не найдено")
    active = await session.scalar(select(DocumentTemplate.id).join(
        DocumentTemplateVersion, DocumentTemplateVersion.template_id == DocumentTemplate.id,
    ).where(DocumentTemplate.tenant_id == scope.tenant_id,
        DocumentTemplate.legal_entity_id == issuer.id, DocumentTemplate.doc_type == TYPE,
        DocumentTemplate.is_active.is_(True), DocumentTemplateVersion.status == "active",
        DocumentTemplateVersion.renderer == "docx"))
    if active is not None:
        return
    existing = await session.scalar(select(DocumentTemplate.id).where(
        DocumentTemplate.tenant_id == scope.tenant_id, DocumentTemplate.legal_entity_id == issuer.id,
        DocumentTemplate.doc_type == TYPE, DocumentTemplate.name == NAME,
    ))
    if existing is not None:
        raise ManagedDocumentConflictError("Начальный шаблон заявления отключён или не имеет активной версии. Проверьте настройки документов.")
    if storage is None:
        raise ManagedDocumentConflictError("Для начального шаблона заявления требуется хранилище документов")
    content = await asyncio.to_thread(template_bytes)
    contract = NativeTemplatePlaceholderContract.create(field_catalog=FIELDS)
    template = DocumentTemplate(tenant_id=scope.tenant_id, legal_entity_id=issuer.id,
        name=NAME, doc_type=TYPE, is_default=True,
        description="Редактируемая форма. Сверьте текст и факты с требованиями конкретной закупки перед выпуском.")
    session.add(template)
    await session.flush()
    source = await storage.save(tenant_id=scope.tenant_id, template_id=template.id, version=1,
        filename="participant-statement-v1.docx", content=content)
    session.add(DocumentTemplateVersion(template_id=template.id, version=1, status="active", renderer="docx",
        source_storage_key=source.storage_key, source_filename=source.filename,
        checksum_sha256=source.checksum_sha256, placeholder_schema=contract.as_persisted_schema(),
        change_note="Начальная редактируемая форма заявления участника"))
    await session.flush()
