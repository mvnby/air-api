"""MCP adapters for the same diagnostics and external file commands used by Manager."""

from urllib.parse import urlencode

from core.config import settings
from crud.connector_order_documents import list_documents
from modules.documents.application.draft_parameters import draft_revision
from modules.documents.application.external_order_documents import (
    EXTERNAL_DOCUMENT_ORIGIN,
    ExternalDocumentFileSource,
    ExternalOrderDocumentService,
)
from modules.documents.application.order_completion_acts import OrderCompletionActService
from modules.documents.application.order_technical_acts import OrderTechnicalActService
from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
from schemas_connector_mcp import ConnectorWriteResult
from schemas_connector_order_documents import OrderDocumentSummary, OrderDocumentsListResult, OrderExternalDocumentSaved
from schemas_order_diagnostics import PrepareOrderTechnicalActInput
from services.connector_file_service import ConnectorFileError, ConnectorFileService, ConnectorFileUnavailable
from services.document_service import DocumentService
from services.document_upload_validation import ExternalDocumentValidationUnavailable
from services.order_inspection_service import OrderInspectionService
from services.private_attachment_storage_service import get_private_attachment_storage


class OrderDocumentUploadFallback(RuntimeError):
    def __init__(self, manager_url: str, *, code: str, status: int, message: str):
        super().__init__(message)
        self.manager_url = manager_url
        self.code = code
        self.status = status


def document_manager_url(order_id, *, document_id=None, proposal_id=None, **parameters):
    query = {"section": "documents"}
    if document_id is not None:
        query["documentId"] = document_id
    if proposal_id is not None:
        query["proposalId"] = proposal_id
    query.update(parameters)
    return f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/{order_id}?{urlencode(query)}"


def _origin(document):
    if document.origin == EXTERNAL_DOCUMENT_ORIGIN:
        return "external_upload"
    if DocumentService._is_native_managed_document(document):
        return "native_generated"
    return "legacy"


def _scope_ids(metadata, many_key, single_key=None):
    values = metadata.get(many_key)
    if isinstance(values, list):
        return [value for value in values if type(value) is int and value > 0]
    single = metadata.get(single_key) if single_key is not None else None
    return [single] if type(single) is int and single > 0 else []


def _summary(document, file_version, artifacts):
    meta = document.scope_meta if isinstance(document.scope_meta, dict) else {}
    origin = _origin(document)
    return OrderDocumentSummary(
        order_id=document.order_id,
        document_id=document.id,
        document_type=document.doc_type,
        origin=origin,
        status=document.status,
        external_status=document.external_status,
        number=document.number,
        document_date=document.official_date or document.date.date(),
        proposal_id=document.proposal_id,
        base_document_id=document.base_document_id,
        base_customer_contract_id=document.base_customer_contract_id,
        site_ids=_scope_ids(meta, "site_ids", "site_id"),
        equipment_ids=_scope_ids(meta, "equipment_ids"),
        revision=draft_revision(document, artifacts) if origin == "native_generated" else None,
        file_version=file_version or 0,
        manager_url=document_manager_url(document.order_id, document_id=document.id, proposal_id=document.proposal_id),
    )


async def list_order_documents(session, actor, inputs):
    await ExternalOrderDocumentService.get_order(session, actor.tenant_scope, inputs.order_id)
    rows, total, artifacts = await list_documents(session, scope=actor.tenant_scope, inputs=inputs)
    return OrderDocumentsListResult(
        items=[_summary(document, version, artifacts.get(document.id, ())) for document, version in rows],
        total=total,
        has_more=inputs.offset + len(rows) < total,
        manager_url=document_manager_url(inputs.order_id),
        upload_manager_url=document_manager_url(inputs.order_id, action="uploadExternalDocument"),
    )


def _file_source(file, manager_url):
    if file is None:
        raise OrderDocumentUploadFallback(
            manager_url, code="file_required", status=400,
            message="ChatGPT did not supply a file. Attach the file in Manager or retry after selecting it in ChatGPT.",
        )

    async def load():
        try:
            return await ConnectorFileService.download_attachment(file)
        except ConnectorFileUnavailable as exc:
            raise OrderDocumentUploadFallback(
                manager_url, code="retryable", status=503,
                message="ChatGPT file delivery was unavailable. Use Manager upload or retry with the same file and key.",
            ) from exc
        except ConnectorFileError as exc:
            raise OrderDocumentUploadFallback(
                manager_url, code="invalid_file", status=400,
                message="ChatGPT could not deliver this file. Select a supported file or upload it in Manager.",
            ) from exc

    return ExternalDocumentFileSource(file.file_name, file.mime_type, file.file_id, load)


async def _write_result(session, actor, outcome):
    document = await ExternalOrderDocumentService.get_document(
        session, actor.tenant_scope, outcome.value.document_id,
    )
    return ConnectorWriteResult[OrderExternalDocumentSaved](result=OrderExternalDocumentSaved(
        order_id=document.order_id,
        document_id=document.id,
        document_type=document.doc_type,
        origin=_origin(document),
        external_status=document.external_status,
        file_version=outcome.value.file_version,
        manager_url=document_manager_url(document.order_id, document_id=document.id, proposal_id=document.proposal_id),
    ), replayed=outcome.replayed)


async def write_external_order_document(session, actor, name, inputs):
    service = ExternalOrderDocumentService
    scope = actor.tenant_scope
    await service.get_order(session, scope, inputs.order_id)
    common = {"actor": actor, "idempotency_key": inputs.idempotency_key}
    if name == "attach_order_document_file":
        document = await service.get_document(session, scope, inputs.document_id)
        if document.order_id != inputs.order_id:
            raise LookupError("Document not found on this order")
        fallback = document_manager_url(
            inputs.order_id, document_id=document.id, proposal_id=document.proposal_id,
            action="attachExternalDocument", fileRole=inputs.file_role,
        )
        operation = service.attach(
            session, document_id=document.id, file_role=inputs.file_role, expected_version=inputs.expected_version,
            source=_file_source(inputs.file, fallback), **common,
        )
    else:
        contract = name == "register_external_order_contract"
        parameters = {"documentType": "contract"} if contract else {}
        fallback = document_manager_url(inputs.order_id, action="uploadExternalDocument", **parameters)
        metadata_only = contract and inputs.metadata_only
        if metadata_only and inputs.file is not None:
            raise ValueError("Select a file or explicitly register metadata only")
        operation = service.create(
            session, order_id=inputs.order_id, payload=inputs.payload,
            source=None if metadata_only else _file_source(inputs.file, fallback), **common,
        )
    try:
        outcome = await operation
    except ExternalDocumentValidationUnavailable as exc:
        raise OrderDocumentUploadFallback(
            fallback, code="retryable", status=503,
            message="Document validation is temporarily unavailable. Retry with the same file and key.",
        ) from exc
    return await _write_result(session, actor, outcome)


async def execute_order_document_workflow_tool(session, actor, name, inputs):
    if name == "get_order_inspection":
        return await OrderInspectionService.read(session, actor, inputs)
    if name == "get_order_completion_act_source":
        return await OrderCompletionActService.source(session, actor, inputs)
    if name == "save_order_inspection":
        outcome = await OrderInspectionService.save(session, actor, inputs)
    elif name == "prepare_order_completion_act":
        outcome = await OrderCompletionActService.prepare(
            session, actor, inputs, template_storage=PrivateTemplateSourceStorage(get_private_attachment_storage()),
        )
    else:
        outcome = await OrderTechnicalActService.prepare(
            session, actor, PrepareOrderTechnicalActInput.model_validate(inputs.model_dump()),
            template_storage=PrivateTemplateSourceStorage(get_private_attachment_storage()),
        )
    return {"result": outcome.value, "replayed": outcome.replayed}
