"""Issue saved CRM documents and read their immutable official PDF for Telegram."""

from collections import defaultdict
from hashlib import sha256
import json

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from api_contracts.bot_order_issuance import BotOrderIssuance
from models import DocumentArtifact, DocumentLegalEntity, OrderDocument, OrderStatus
from modules.documents.application import ManagedDocumentService
from modules.documents.application.contract_act_numbers import ContractActNumberConfirmationRequired
from modules.documents.application.customer_readiness import (
    READINESS_DOCUMENT_TYPES,
    require_issue_readiness,
)
from modules.documents.application.draft_parameters import draft_revision
from modules.documents.application.draft_source_context import validate_draft_source_context
from modules.documents.application.errors import (
    ManagedDocumentConflictError,
    ManagedDocumentGenerationError,
    ManagedDocumentNotFoundError,
)
from modules.documents.application.facsimile_context import MAX_PDF_BYTES
from modules.documents.application.framework_contracts import is_framework
from modules.documents.application.template_selection import load_document_template_version
from modules.documents.application.waybill_paper import check_waybill_tax_profile
from modules.documents.domain import B2C_NATIVE_DOCUMENT_TYPES
from modules.documents.domain.placeholder_catalog import SUPPORTED_NATIVE_DOCUMENT_TYPES
from modules.documents.infrastructure.artifact_storage import PrivateDocumentArtifactStorage
from modules.documents.infrastructure.configured_pdf import configured_pdf_converter
from modules.documents.infrastructure.renderers.pdf import UnavailablePdfConverter
from services.authenticated_command_service import AuthenticatedCommandService
from services.bot_order_documents import _BotDocumentTemplateStorage, _private_storage
from services.inbox_eligibility import require_unarchived_inbox
from services.private_attachment_storage_service import PrivateAttachmentTooLarge
from services.public_write_idempotency_service import PublicWriteCommandResponse
from services.tenant_entity_access_service import TenantEntityAccessService


PUBLISHED = frozenset({"issued", "sent", "signed"})
SPECIALIST_ISSUANCE = {
    "participant_statement": "Подтвердите текст и требования закупки в Manager.",
    "contract_amendment": "Подтвердите согласованный объём и сумму допсоглашения в Manager.",
}


class _IssueReceipt(BaseModel):
    order_id: int
    document_id: int
    reserved_revision: str


def _revision(document, artifacts=()):
    # Include frozen parameters and actual bytes plus the document/variant/issuer binding.
    identity = (
        document.id, document.order_id, document.proposal_id, document.doc_type, document.business_role,
        document.legal_entity_id, document.document_template_id, document.base_document_id,
        document.base_customer_contract_id, document.contract_act_number, document.scope_meta,
        draft_revision(document, artifacts),
    )
    return sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()


async def _order_block(session, scope, order_id, status):
    if scope.demo_read_only:
        return "Официальный выпуск недоступен в демо."
    if status == OrderStatus.CLOSED:
        return "Заказ закрыт. Документы доступны для просмотра."
    if status not in {OrderStatus.NEGOTIATION, OrderStatus.EXECUTION}:
        return "Выпуск доступен в открытом заказе."
    try:
        await require_unarchived_inbox(session, "order", order_id)
    except ValueError as exc:
        return str(exc)
    return None


def _draft_block(document, issuer, artifacts, order_block, customer_id):
    if document.origin == "external_upload":
        return "Документ загружен извне. Его выпуск оформляется у источника."
    if not document.status or not document.internal_reference:
        return "Документ создан в прежнем контуре. Его можно открыть в Manager."
    if document.status == "void":
        return "Документ аннулирован."
    if document.status == "replaced":
        return "Документ заменён."
    if order_block:
        return order_block
    if document.doc_type in SPECIALIST_ISSUANCE:
        return SPECIALIST_ISSUANCE[document.doc_type]
    if document.doc_type not in SUPPORTED_NATIVE_DOCUMENT_TYPES:
        return "Для этого вида документа используется отдельное оформление в Manager."
    if document.replaces_document_id:
        return "Для выпуска замены проверьте исходный документ в Manager."
    if document.google_file_id or document.google_edit_url or any(a.kind == "source_docx" for a in artifacts):
        return "Черновик редактировался в Google Docs. Проверьте синхронизацию и выпустите его в Manager."
    if artifacts:
        return "В черновике обнаружены файлы выпуска. Проверьте его состояние в Manager."
    snapshot = document.render_snapshot
    if not document.document_template_id or not document.template_version_id or not isinstance(snapshot, dict) or not snapshot:
        return "У черновика отсутствует сохранённый снимок или версия шаблона."
    if issuer is None or issuer.status != "active":
        return "Юридическое лицо документа недоступно или больше не активно."
    meta = snapshot.get("meta") or {}
    if not isinstance(meta, dict):
        return "Проверьте сохранённый снимок документа в Manager."
    if "customer_id" in meta and meta["customer_id"] != customer_id:
        return "Клиент заказа изменился. Подготовьте новый черновик."
    return None


async def _readiness_block(session, scope, document):
    try:
        template, version = await load_document_template_version(session, tenant_scope=scope, document=document)
        if template.doc_type != document.doc_type:
            return "Сохранённый шаблон относится к другому виду документа."
        if not isinstance(document.render_snapshot.get("values"), dict):
            return "В сохранённом снимке документа отсутствуют реквизиты."
        check_waybill_tax_profile(document.render_snapshot, version.placeholder_schema, document.doc_type)
        readiness = (document.render_snapshot.get("meta") or {}).get("customer_readiness")
        # Business documents permit handwriting in advisory customer fields.
        if document.doc_type in B2C_NATIVE_DOCUMENT_TYPES and isinstance(readiness, dict):
            require_issue_readiness(readiness)
        await validate_draft_source_context(session, document)
    except (ManagedDocumentConflictError, ManagedDocumentNotFoundError) as exc:
        return str(exc)
    except NoResultFound:
        return "Сохранённое предложение недоступно. Подготовьте новый черновик."
    except (AttributeError, KeyError, TypeError, ValueError):
        return "Проверьте сохранённый снимок и версию шаблона в Manager."
    if isinstance(configured_pdf_converter(), UnavailablePdfConverter):
        return "Сервис подготовки PDF недоступен."
    return None


async def read_issuance(session, actor, detail):
    scope = actor.tenant_scope
    order_id = detail["id"]
    documents = await ManagedDocumentService.list_for_order(session, tenant_scope=scope, order_id=order_id)
    if not documents:
        return []
    order_block = await _order_block(session, scope, order_id, detail["status"])
    issuers = {
        issuer.id: issuer for issuer in (await session.scalars(select(DocumentLegalEntity).where(
            DocumentLegalEntity.tenant_id == scope.tenant_id,
            DocumentLegalEntity.id.in_({doc.legal_entity_id for doc in documents if doc.legal_entity_id}),
        ).execution_options(populate_existing=True))).all()
    }
    artifacts_by_document = defaultdict(list)
    for artifact in (await session.scalars(select(DocumentArtifact).where(
        DocumentArtifact.tenant_id == scope.tenant_id,
        DocumentArtifact.order_document_id.in_([doc.id for doc in documents]),
        DocumentArtifact.is_authoritative.is_(True),
    ))).all():
        artifacts_by_document[artifact.order_document_id].append(artifact)
    customer_id = (detail.get("customer") or {}).get("id")
    capabilities = []
    for document in documents:
        artifacts = artifacts_by_document[document.id]
        issuer = issuers.get(document.legal_entity_id)
        snapshot = document.render_snapshot
        values = snapshot.get("values") if isinstance(snapshot, dict) else None
        issuer_name = values.get("seller.legal_name") if isinstance(values, dict) else None
        if not isinstance(issuer_name, str) or not issuer_name:
            issuer_name = issuer.legal_name or issuer.display_name if issuer else None
        state, revision, can_download = "blocked", None, False
        if document.status in PUBLISHED and not document.origin:
            state = "issued"
            pdf = next((artifact for artifact in artifacts if artifact.kind == "pdf"), None)
            if scope.demo_read_only:
                reason = "Получение PDF недоступно в демо."
            elif pdf is None:
                reason = "Сохранённый официальный PDF не найден."
            elif pdf.size_bytes > MAX_PDF_BYTES:
                reason = "PDF превышает допустимый размер для отправки в Telegram."
            else:
                can_download, reason = True, None
        else:
            reason = _draft_block(document, issuer, artifacts, order_block, customer_id)
            if reason is None:
                reason = await _readiness_block(session, scope, document)
            if reason is None:
                state = "reserved" if document.official_number else "ready"
                revision = _revision(document, artifacts)
        capabilities.append(BotOrderIssuance(
            document_id=document.id, state=state, revision=revision, reason=reason,
            document_type=document.doc_type, legal_entity_name=issuer_name, can_download_pdf=can_download,
        ))
    return capabilities


async def _lock_document(session, scope, order_id, document_id):
    document = await session.scalar(select(OrderDocument).where(
        OrderDocument.tenant_id == scope.tenant_id, OrderDocument.order_id == order_id,
        OrderDocument.id == document_id,
    ).with_for_update().execution_options(populate_existing=True))
    if document is None:
        raise ManagedDocumentNotFoundError("Документ не найден в заказе.")
    return document


async def _issuer_for_issue(session, scope, document, *, reserving=False):
    statement = select(DocumentLegalEntity).where(
        DocumentLegalEntity.id == document.legal_entity_id,
        DocumentLegalEntity.tenant_id == scope.tenant_id,
    ).execution_options(populate_existing=True)
    # Framework registration checks and locks the issuer together with the customer.
    if not (reserving and is_framework(document)):
        statement = statement.with_for_update(read=True)
    return await session.scalar(statement)


async def _issue(session, scope, document, *, reserve_only=False):
    private = _private_storage()
    template_storage = _BotDocumentTemplateStorage(private)
    converter = configured_pdf_converter()
    if isinstance(converter, UnavailablePdfConverter):
        raise HTTPException(503, "Сервис подготовки PDF недоступен.")
    try:
        if reserve_only and document.doc_type not in READINESS_DOCUMENT_TYPES:
            template, version = await load_document_template_version(session, tenant_scope=scope, document=document)
            await template_storage.read_persisted(
                tenant_id=scope.tenant_id, template_id=template.id, version=version.version,
                storage_key=version.source_storage_key, filename=version.source_filename or "template.docx",
                checksum_sha256=version.checksum_sha256,
            )
        return await ManagedDocumentService.issue(
            session, tenant_scope=scope, document_id=document.id,
            template_storage=template_storage, artifact_storage=PrivateDocumentArtifactStorage(private),
            pdf_converter=converter, commit=False, reserve_only=reserve_only,
        )
    except ContractActNumberConfirmationRequired as exc:
        raise ManagedDocumentConflictError(f"{exc} Завершите сверку в Manager.") from exc
    except ManagedDocumentGenerationError as exc:
        headers = {"X-Kitlane-Document-State": "number-reserved"} if not reserve_only and document.official_number else None
        raise HTTPException(503, str(exc), headers=headers) from exc


async def issue_order_document(session, actor, order_id, request, *, load_order):
    """A receipt binds manager consent to one canonical reservation and finalization."""
    scope, change = actor.tenant_scope, request.change
    payload = {"order_id": order_id, "expected_revision": request.expected_revision,
               "change": change.model_dump(mode="json", exclude_unset=True)}
    key = str(request.idempotency_key)

    async def reserve():
        desk, detail = await load_order()
        if desk.revision != request.expected_revision:
            raise ManagedDocumentConflictError("Заказ изменился. Обновите карточку и проверьте документ.")
        document = await _lock_document(session, scope, order_id, change.document_id)
        capability = next((item for item in desk.issuance if item.document_id == document.id), None)
        if capability is None:
            raise ManagedDocumentNotFoundError("Документ не найден в заказе.")
        if capability.state == "issued":
            raise ManagedDocumentConflictError("Документ уже выпущен.")
        if capability.state == "blocked":
            raise ManagedDocumentConflictError(capability.reason)
        artifacts = await ManagedDocumentService.list_artifacts(session, tenant_scope=scope, document_id=document.id)
        if (capability.revision != change.expected_document_revision
                or _revision(document, artifacts) != change.expected_document_revision):
            raise ManagedDocumentConflictError("Черновик изменился. Обновите заказ и проверьте документ.")
        issuer = await _issuer_for_issue(session, scope, document, reserving=capability.state == "ready")
        customer_id = (detail.get("customer") or {}).get("id")
        if reason := _draft_block(document, issuer, artifacts, None, customer_id):
            raise ManagedDocumentConflictError(reason)
        if capability.state == "ready":
            await _issue(session, scope, document, reserve_only=True)
        receipt = _IssueReceipt(order_id=order_id, document_id=document.id, reserved_revision=_revision(document))
        return PublicWriteCommandResponse(value=receipt, resource_type="order_document", resource_id=document.id)

    reservation = await AuthenticatedCommandService.execute(
        session, actor=actor, command_name="order.telegram_change", idempotency_key=key,
        payload=payload, response_model=_IssueReceipt, operation=reserve,
    )
    receipt = reservation.value

    async def finalize():
        order = await TenantEntityAccessService.get_order(
            session, order_id, tenant_scope=scope, for_update=True, populate_existing=True,
        )
        if order is None or order.status == OrderStatus.NEW_LEAD:
            raise ManagedDocumentNotFoundError("Заказ не найден.")
        document = await _lock_document(session, scope, order_id, receipt.document_id)
        if document.status not in PUBLISHED:
            if document.status != "draft" or not document.official_number:
                raise ManagedDocumentConflictError("Зарезервированный черновик больше недоступен для выпуска.")
            artifacts = await ManagedDocumentService.list_artifacts(session, tenant_scope=scope, document_id=document.id)
            if _revision(document, artifacts) != receipt.reserved_revision:
                raise ManagedDocumentConflictError("Зарезервированный черновик изменился. Проверьте документ в Manager.")
            issuer = await _issuer_for_issue(session, scope, document)
            order_reason = await _order_block(session, scope, order_id, order.status)
            if reason := _draft_block(document, issuer, artifacts, order_reason, order.customer_id):
                raise ManagedDocumentConflictError(reason)
            await _issue(session, scope, document)
        return PublicWriteCommandResponse(value=receipt, resource_type="order_document", resource_id=document.id)

    await AuthenticatedCommandService.execute(
        session, actor=actor, command_name="order.telegram_issue_finalize",
        idempotency_key=key, payload=payload, response_model=_IssueReceipt, operation=finalize,
    )


async def issued_pdf(session, scope, order_id, document_id):
    if scope.demo_read_only:
        raise HTTPException(403, "Получение PDF недоступно в демо.")
    order = await TenantEntityAccessService.get_order(session, order_id, tenant_scope=scope)
    if order is None or order.status == OrderStatus.NEW_LEAD:
        raise ManagedDocumentNotFoundError("Заказ не найден.")
    document = await ManagedDocumentService.get_document(session, tenant_scope=scope, document_id=document_id)
    if document.order_id != order_id:
        raise ManagedDocumentNotFoundError("Документ не найден в заказе.")
    if document.status not in PUBLISHED or document.origin:
        raise ManagedDocumentConflictError("Сохранённый официальный PDF доступен после выпуска документа.")
    artifacts = await ManagedDocumentService.list_artifacts(session, tenant_scope=scope, document_id=document_id)
    artifact = next((item for item in artifacts if item.kind == "pdf"), None)
    if artifact is None:
        raise ManagedDocumentNotFoundError("Сохранённый официальный PDF не найден.")
    if artifact.size_bytes > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF превышает допустимый размер для отправки в Telegram.")
    try:
        storage = PrivateDocumentArtifactStorage(_private_storage(artifact.provider))
        content = await storage.read(ManagedDocumentService.stored_artifact(artifact), max_bytes=MAX_PDF_BYTES)
        if not content.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF signature")
        return content
    except PrivateAttachmentTooLarge as exc:
        raise HTTPException(413, "PDF превышает допустимый размер для отправки в Telegram.") from exc
    except Exception as exc:
        raise HTTPException(503, "Не удалось прочитать сохранённый PDF. Повторите позже.") from exc
