"""Commercial documents for a specific saved order and proposal."""

from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_, select

from api_contracts.bot_order_desk import BotOrderDocument, BotOrderIssuer
from models import Customer, DocumentLegalEntity, DocumentTemplate, DocumentTemplateVersion, Order
from modules.documents.application import DocumentContextSelection, ManagedDocumentService
from modules.documents.application.draft_preview import ManagedDocumentDraftPreviewService
from modules.documents.application.errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from modules.documents.infrastructure.artifact_storage import PrivateDocumentArtifactStorage
from modules.documents.infrastructure.configured_pdf import configured_pdf_converter
from modules.documents.infrastructure.renderers.pdf import PdfConversionError
from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_service import OrderService
from services.private_attachment_storage_service import get_private_attachment_storage
from services.tenant_entity_access_service import TenantEntityAccessService


TITLES = {"offer": "Коммерческое предложение", "invoice": "Счёт", "contract": "Договор", "act": "Акт",
          "tn2": "Товарная накладная", "ttn1": "Товарно-транспортная накладная",
          "consumer_contract": "Договор с физлицом", "retail_receipt": "Товарный чек",
          "warranty_certificate": "Гарантийный талон", "contract_amendment": "Дополнительное соглашение"}
STATES = {"draft": "Черновик", "issued": "Выпущен", "sent": "Отправлен", "signed": "Подписан",
          "void": "Аннулирован", "replaced": "Заменён", "received": "Получен"}
BUSINESS_CUSTOMER_TYPES = ("company", "individual_entrepreneur")


class _BotDocumentTemplateStorage(PrivateTemplateSourceStorage):
    async def read_persisted(self, **source):
        try:
            return await super().read_persisted(**source)
        except Exception as exc:
            raise HTTPException(503, "Не удалось прочитать шаблон документа. Повторите позже.") from exc


class _BotDocumentArtifactStorage(PrivateDocumentArtifactStorage):
    async def read(self, artifact):
        try:
            return await super().read(artifact)
        except Exception as exc:
            raise HTTPException(503, "Не удалось прочитать черновик документа. Повторите позже.") from exc


def _private_storage():
    try:
        return get_private_attachment_storage()
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, "Приватное хранилище документов недоступно. Повторите позже.") from exc


def _google_document_url(raw):
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
        if parts.scheme == "https" and parts.netloc in {"docs.google.com", "drive.google.com"}:
            return raw
    except ValueError:
        pass
    return None


def _previewable(row):
    return row.doc_type in {"offer", "invoice"} and row.status == "draft" and bool(
        row.template_version_id and row.render_snapshot
    )


async def read_documents(session, scope, order_id):
    rows = await ManagedDocumentService.list_for_order(session, tenant_scope=scope, order_id=order_id)
    documents = []
    for row in rows:
        label = TITLES.get(row.doc_type, "Документ")
        number = row.official_number or row.number or row.internal_reference
        documents.append(BotOrderDocument(
            id=row.id, title=f"{label} · {number}" if number else label, proposal_id=row.proposal_id,
            status=STATES.get(row.status or row.external_status, "Сохранён"),
            can_preview=_previewable(row) and not scope.demo_read_only,
            url=_google_document_url(row.google_edit_url) if not scope.demo_read_only else None,
        ))
    return documents


async def draft_issuers(session, scope, detail, followup):
    customer = followup.customer
    if (scope.demo_read_only or not followup.can_edit_details or not customer or customer.type not in BUSINESS_CUSTOMER_TYPES
            or detail["workflow_type"] != "sales_installation" or detail["status"] != "negotiation"
            or detail.get("is_on_hold")):
        return []
    if not await _active_business_customer(session, scope, detail["id"]):
        return []
    # One lookup returns live offer/payment-request templates across this company's issuers.
    rows = (await session.execute(
        select(DocumentLegalEntity.id, DocumentLegalEntity.display_name, DocumentTemplate.doc_type)
        .join(DocumentTemplate, DocumentTemplate.legal_entity_id == DocumentLegalEntity.id)
        .join(DocumentTemplateVersion, DocumentTemplateVersion.template_id == DocumentTemplate.id)
        .where(DocumentLegalEntity.tenant_id == scope.tenant_id, DocumentLegalEntity.status == "active",
               DocumentTemplate.tenant_id == scope.tenant_id, DocumentTemplate.is_active.is_(True),
               DocumentTemplate.doc_type.in_(("offer", "invoice")),
               or_(DocumentTemplate.doc_type == "offer", DocumentTemplate.business_role.is_(None),
                   DocumentTemplate.business_role == "payment_request"),
               DocumentTemplateVersion.renderer == "docx", DocumentTemplateVersion.status == "active")
        .order_by(DocumentLegalEntity.is_default.desc(), DocumentLegalEntity.display_name,
                  DocumentLegalEntity.id, DocumentTemplate.doc_type)
    )).all()
    options = {}
    for issuer_id, name, kind in rows:
        issuer = options.setdefault(issuer_id, BotOrderIssuer(id=issuer_id, name=name, types=[]))
        if kind not in issuer.types:
            issuer.types.append(kind)
    return list(options.values())


async def _active_business_customer(session, scope, order_id, *, lock=False):
    statement = (
        select(Customer.id)
        .join(Order, Order.customer_id == Customer.id)
        .where(Order.id == order_id, TenantEntityAccessService.order_clause(scope),
               TenantEntityAccessService.order_customer_clause(scope),
               Customer.type.in_(BUSINESS_CUSTOMER_TYPES), Customer.is_archived.is_(False))
    )
    if lock:
        statement = statement.with_for_update(of=Customer)
    return await session.scalar(statement) is not None


def saved_proposal(desk, proposal_id):
    proposal = next((p for p in desk.proposals if p.id == proposal_id and not p.is_archived), None)
    if proposal is None:
        raise HTTPException(404, "Вариант заказа недоступен.")
    if not (proposal.product_lines or proposal.service_lines):
        raise HTTPException(422, "Добавьте в вариант оборудование или работы.")
    return proposal


async def prepare_document(session, scope, desk, change):
    """Prepare one saved proposal under the caller's locked order transaction."""
    if scope.demo_read_only:
        raise HTTPException(403, "Сохранение черновика недоступно в демо.")
    saved_proposal(desk, change.proposal_id)
    if not any(i.id == change.legal_entity_id and change.document_type in i.types for i in desk.document_issuers):
        raise HTTPException(409, "Для этого заказа и юрлица нет доступного шаблона.")
    if not await _active_business_customer(session, scope, desk.id, lock=True):
        raise HTTPException(409, "Для черновика нужен действующий клиент — организация или ИП.")
    proposal_id = change.proposal_id
    if proposal_id is None:
        order = await OrderProposalCommandService._load_order_for_write(session, desk.id, tenant_scope=scope)
        proposal = OrderService._selected_proposal(order)
        if proposal is None:
            raise HTTPException(409, "Не удалось закрепить основной вариант заказа. Обновите заказ.")
        proposal_id = proposal.id
    return await ManagedDocumentService.create_draft(
        session, tenant_scope=scope,
        selection=DocumentContextSelection(
            order_id=desk.id, proposal_id=proposal_id, document_type=change.document_type,
            legal_entity_id=change.legal_entity_id, issue_date=datetime.now(ZoneInfo("Europe/Minsk")).date(),
            business_role="payment_request" if change.document_type == "invoice" else None,
        ),
        template_storage=_BotDocumentTemplateStorage(_private_storage()), commit=False,
    )


async def draft_pdf(session, scope, order_id, document_id):
    if scope.demo_read_only:
        raise HTTPException(403, "Скачивание черновика недоступно в демо.")
    document = await ManagedDocumentService.get_document(session, tenant_scope=scope, document_id=document_id)
    if document.order_id != order_id:
        raise HTTPException(404, "Документ не найден в заказе.")
    if not _previewable(document):
        raise HTTPException(409, "Предпросмотр доступен для черновика КП или счёта.")
    private = _private_storage()
    try:
        content, _ = await ManagedDocumentDraftPreviewService.render_pdf(
            session, tenant_scope=scope, document_id=document_id,
            template_storage=_BotDocumentTemplateStorage(private), artifact_storage=_BotDocumentArtifactStorage(private),
            pdf_converter=configured_pdf_converter(),
        )
    except (ManagedDocumentNotFoundError, ManagedDocumentConflictError):
        raise
    except (OSError, ValueError, TypeError, PdfConversionError) as exc:
        raise HTTPException(503, "Не удалось подготовить PDF. Повторите позже.") from exc
    return content
