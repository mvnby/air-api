"""Agent adapter; business rules and snapshots remain in the document module."""

from pydantic import BaseModel
from modules.documents.application import (
    ManagedDocumentService,
    DocumentContextSelection,
)
from modules.documents.application.contract_amendments import (
    list_bases,
    load_basis,
    calculation,
)
from modules.documents.application.customer_readiness import (
    check_saved_document_readiness,
)
from modules.documents.application.draft_parameters import draft_revision
from modules.documents.application.errors import ManagedDocumentNotFoundError
from services.connector_service_order_document import _storage
from services.authenticated_command_service import AuthenticatedCommandService
from services.public_write_idempotency_service import PublicWriteCommandResponse
from schemas_connector_contract_amendment import (
    ContractAmendmentResult,
    AmendmentBasisList,
)
from core.config import settings


class _SavedAmendment(BaseModel):
    id: int


async def read_amendment(session, actor, document_id, *, storage=None):
    doc = await ManagedDocumentService.get_document(
        session, tenant_scope=actor.tenant_scope, document_id=document_id
    )
    if doc.doc_type != "contract_amendment":
        raise ManagedDocumentNotFoundError("Дополнительное соглашение не найдено")
    basis = await load_basis(
        session,
        scope=actor.tenant_scope,
        order_id=doc.order_id,
        basis_id=doc.base_document_id,
        require_active=False,
    )
    _, _, current = await calculation(session, basis)
    snapshot = doc.render_snapshot
    meta, values = snapshot["meta"], snapshot["values"]
    try:
        readiness = await check_saved_document_readiness(
            session,
            tenant_scope=actor.tenant_scope,
            document=doc,
            template_storage=storage or _storage(),
        )
    except OSError:
        # The durable receipt and draft may already be committed. Keep their IDs
        # usable after a storage outage instead of leaving the caller guessing.
        readiness = {
            "checked": False,
            "can_issue": False,
            "missing_fields": [
                {
                    "field": "template.source",
                    "label": "Шаблон временно недоступен. Повторите чтение по сохранённому ID",
                    "critical": True,
                }
            ],
        }
    if doc.status == "draft" and basis.status not in {"issued", "sent", "signed"}:
        readiness = {
            "checked": True,
            "can_issue": False,
            "missing_fields": [
                {
                    "field": "basis.status",
                    "label": "Исходный договор больше не действует",
                    "critical": True,
                }
            ],
        }
    artifacts = await ManagedDocumentService.list_artifacts(
        session, tenant_scope=actor.tenant_scope, document_id=doc.id
    )
    version = meta["amendment"]["basis_revision"]
    return ContractAmendmentResult(
        order_id=doc.order_id,
        base_document_id=doc.base_document_id,
        document_id=doc.id,
        status=doc.status,
        revision=draft_revision(doc, artifacts),
        basis_revision=version,
        current_basis_revision=current,
        stale=doc.status == "draft" and current != version,
        original_amount=values["amendment.original_amount"],
        other_amendments_amount=values["amendment.other_amount"],
        change_amount=values["totals.amount"],
        new_total=values["amendment.new_total"],
        currency=values["totals.currency"],
        amendment_terms=meta["draft_parameters"]["amendment_terms"],
        readiness=readiness,
        manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/{doc.order_id}?section=documents&documentId={doc.id}",
    )


async def execute_amendment_tool(session, actor, name, data, *, storage=None):
    if name == "list_contract_amendment_bases":
        return AmendmentBasisList(
            order_id=data.order_id,
            items=await list_bases(
                session, scope=actor.tenant_scope, order_id=data.order_id
            ),
        )
    if name == "get_contract_amendment":
        return await read_amendment(session, actor, data.document_id, storage=storage)

    async def operation():
        basis = await load_basis(
            session,
            scope=actor.tenant_scope,
            order_id=data.order_id,
            basis_id=data.base_document_id,
        )
        doc = await ManagedDocumentService.create_draft(
            session,
            tenant_scope=actor.tenant_scope,
            selection=DocumentContextSelection(
                order_id=data.order_id,
                document_type="contract_amendment",
                legal_entity_id=basis.legal_entity_id,
                issue_date=data.issue_date,
                base_document_id=basis.id,
                amendment_terms=data.amendment_terms,
                amendment_basis_revision=data.expected_basis_revision,
            ),
            template_id=data.template_id,
            template_storage=storage or _storage(),
            commit=False,
        )
        return PublicWriteCommandResponse(
            _SavedAmendment(id=doc.id),
            resource_type="order_document",
            resource_id=doc.id,
        )

    result = await AuthenticatedCommandService.execute(
        session,
        actor=actor,
        command_name=name,
        idempotency_key=data.idempotency_key,
        payload=data.model_dump(mode="json", exclude={"idempotency_key"}),
        response_model=_SavedAmendment,
        operation=operation,
    )
    return {
        "result": await read_amendment(
            session, actor, result.value.id, storage=storage
        ),
        "replayed": result.replayed,
    }
