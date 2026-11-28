"""Validate the source versions frozen by connector document preparation."""

from modules.documents.domain import B2C_NATIVE_DOCUMENT_TYPES
from services.order_proposal_version import proposal_version
from services.order_sales_context_version import sales_order_context_version

from .errors import ManagedDocumentConflictError


async def validate_draft_source_context(session, document):
    """The issuing caller holds the order lock while comparing versions."""
    meta = (document.render_snapshot or {}).get("meta") or {}
    connector_version = meta.get("connector_proposal_version")
    inherits_consumer_snapshot = (
        document.doc_type in B2C_NATIVE_DOCUMENT_TYPES
        and document.replaces_document_id is not None
    )
    if connector_version is not None and not inherits_consumer_snapshot:
        current_version = await proposal_version(session, document.order_id, document.proposal_id)
        if connector_version != current_version:
            raise ManagedDocumentConflictError(
                "Предложение изменилось после подготовки документа. Создайте новый черновик по актуальным строкам."
            )
    sales_context_version = meta.get("sales_order_context_version")
    if document.doc_type == "offer" and sales_context_version is not None:
        current_sales_context = await sales_order_context_version(session, document.order_id, document.proposal_id)
        if sales_context_version != current_sales_context:
            raise ManagedDocumentConflictError(
                "Контекст заказа изменился после подготовки предложения. Создайте новый черновик по актуальным условиям."
            )
