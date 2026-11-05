"""Prepare and inspect native drafts for explicitly selected service proposals.

The caller owns the transaction and idempotency receipt. Draft snapshots are never
rewritten: a new draft preserves both prior drafts and issued documents.
"""

from decimal import Decimal

from fastapi import HTTPException
from sqlmodel import select

from core.config import settings
from models import DocumentLegalEntity
from modules.documents.application import DocumentContextSelection, ManagedDocumentService
from modules.documents.application.customer_readiness import check_saved_document_readiness
from modules.documents.application.errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from modules.documents.domain.business_terms import BusinessDocumentTerms, PaymentScheduleItem
from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
from schemas_connector_service_order_document import ServiceOrderContractResult
from services.order_proposal_version import proposal_version
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_service import OrderService
from services.private_attachment_storage_service import get_private_attachment_storage
from services.tenant_entity_access_service import TenantEntityAccessService


def _storage():
    return PrivateTemplateSourceStorage(get_private_attachment_storage())


def _url(order_id, proposal_id, document_id):
    return f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/{order_id}?proposalId={proposal_id}&section=documents&documentId={document_id}"


async def _issuer(session, scope, requested):
    query = (
        select(DocumentLegalEntity)
        .where(
            DocumentLegalEntity.tenant_id == scope.tenant_id,
            DocumentLegalEntity.status == "active",
        )
        .order_by(DocumentLegalEntity.id)
    )
    entities = list((await session.execute(query)).scalars().all())
    if requested is not None:
        issuer = next((item for item in entities if item.id == requested), None)
        if issuer is None:
            raise HTTPException(404, "Active document issuer not found")
        return issuer
    defaults = [item for item in entities if item.is_default]
    if len(defaults) == 1:
        return defaults[0]
    if len(entities) == 1:
        return entities[0]
    choices = ", ".join(f"{item.id}: {item.display_name}" for item in entities) or "none"
    raise HTTPException(
        409, f"Choose an active document issuer (legal_entity_id) in Manager; available: {choices}"
    )


async def _result(session, ctx, document, *, template_storage=None):
    order = await TenantEntityAccessService.get_order(session, document.order_id, tenant_scope=ctx.tenant_scope)
    if order is None:
        raise HTTPException(404, "Order not found")
    snapshot = document.render_snapshot or {}
    meta = snapshot.get("meta") or {}
    version = meta.get("connector_proposal_version")
    if version is None or document.doc_type not in {"contract", "invoice"} or not document.proposal_id:
        raise HTTPException(404, "Service-order draft not found")
    await _issuer(session, ctx.tenant_scope, document.legal_entity_id)
    current = await proposal_version(session, document.order_id, document.proposal_id)
    readiness = await check_saved_document_readiness(
        session,
        tenant_scope=ctx.tenant_scope,
        document=document,
        template_storage=template_storage or _storage(),
    )
    stale = version != current
    values = snapshot.get("values") or {}
    return ServiceOrderContractResult(
        order_id=document.order_id,
        proposal_id=document.proposal_id,
        document_id=document.id,
        legal_entity_id=document.legal_entity_id,
        document_type=document.doc_type,
        business_role=document.business_role,
        status=document.status,
        proposal_version=version,
        current_proposal_version=current,
        stale=stale,
        customer_ready_and_current=document.status == "draft"
        and not stale
        and readiness.get("can_issue", False),
        readiness=readiness,
        total_byn=str(values.get("totals.amount", "")),
        vat_label=str(values.get("totals.vat_label", "")),
        manager_url=_url(document.order_id, document.proposal_id, document.id),
        payment_terms=values.get("payment.summary") or None,
    )


async def prepare_service_order_contract(session, ctx, data, *, template_storage=None):
    scope = ctx.tenant_scope
    try:
        order = await OrderProposalCommandService._load_order_for_write(
            session, data.order_id, tenant_scope=scope
        )
    except ValueError as exc:
        raise HTTPException(404, "Order not found") from exc
    if OrderService._status_value(order.status) != "negotiation":
        raise ManagedDocumentConflictError("Document drafts require an order in negotiation")
    if order.workflow_type not in {"repair", "service_work", "maintenance"}:
        raise HTTPException(409, "Choose a repair, maintenance or service order in Manager")
    customer = (
        await TenantEntityAccessService.get_customer(session, order.customer_id, tenant_scope=scope)
        if order.customer_id
        else None
    )
    party_type = str(getattr(customer.type, "value", customer.type)) if customer else None
    if customer is None or customer.is_archived or party_type not in {"company", "individual_entrepreneur"}:
        raise HTTPException(
            409,
            "Choose an active company or entrepreneur customer in the Manager order; individuals require a different document type",
        )
    proposal = next((p for p in order.proposals if p.id == data.proposal_id and not p.is_archived), None)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    if not any(line.proposal_id == proposal.id for line in order.service_links):
        raise ManagedDocumentConflictError("Add at least one service to the selected proposal")
    version = await proposal_version(session, order.id, proposal.id)
    if version != data.expected_version:
        raise ManagedDocumentConflictError(
            "Proposal changed; read its current version before preparing the draft"
        )
    issuer = await _issuer(session, scope, data.legal_entity_id)
    scenario = "installation" if order.workflow_type == "service_work" else order.workflow_type
    terms = (
        BusinessDocumentTerms(
            contract_scenario=scenario,
            payment_schedule=(
                PaymentScheduleItem(
                    share_percent=Decimal("100"), due_event="before_work", due_day_kind="banking"
                ),
            ),
        )
        if data.document_type == "contract"
        else None
    )
    selection = DocumentContextSelection(
        order_id=order.id,
        proposal_id=proposal.id,
        legal_entity_id=issuer.id,
        document_type=data.document_type,
        issue_date=data.issue_date,
        business_terms=terms,
        business_role=data.business_role,
    )
    storage = template_storage or _storage()
    try:
        document = await ManagedDocumentService.create_draft(
            session,
            tenant_scope=scope,
            selection=selection,
            template_id=data.template_id,
            template_storage=storage,
            commit=False,
        )
    except ManagedDocumentNotFoundError as exc:
        raise HTTPException(
            409, f"{exc}. Выберите подходящий активный шаблон DOCX в настройках документов Manager."
        ) from exc
    snapshot = dict(document.render_snapshot)
    meta = dict(snapshot.get("meta") or {})
    meta["connector_proposal_version"] = version
    snapshot["meta"] = meta
    document.render_snapshot = snapshot
    session.add(document)
    await session.flush()
    return await _result(session, ctx, document, template_storage=storage)


async def get_service_order_contract(session, ctx, data, *, template_storage=None):
    document = await ManagedDocumentService.get_document(
        session, tenant_scope=ctx.tenant_scope, document_id=data.document_id
    )
    return await _result(session, ctx, document, template_storage=template_storage)
