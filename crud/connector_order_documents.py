"""Read a bounded projection of one authorized order's documents."""

from collections import defaultdict

from sqlalchemy import cast, func, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import select

from models import Customer, DocumentArtifact, Order, OrderDocument, OrderDocumentExternalFile
from services.tenant_entity_access_service import TenantEntityAccessService as Access


async def list_documents(session, *, scope, inputs):
    documents = OrderDocument
    files = OrderDocumentExternalFile
    filters = [
        documents.order_id == inputs.order_id,
        Access.order_clause(scope),
        Access.order_customer_clause(scope),
        or_(documents.tenant_id == scope.tenant_id, documents.tenant_id.is_(None)),
    ]
    metadata = cast(documents.scope_meta, JSONB)
    if inputs.document_type is not None:
        filters.append(documents.doc_type == inputs.document_type)
    if inputs.site_id is not None:
        filters.append(or_(
            metadata.contains({"site_id": inputs.site_id}),
            metadata.contains({"site_ids": [inputs.site_id]}),
        ))
    if inputs.equipment_id is not None:
        filters.append(metadata.contains({"equipment_ids": [inputs.equipment_id]}))
    file_version = (
        select(func.max(files.version))
        .where(files.document_id == documents.id, files.tenant_id == scope.tenant_id)
        .correlate(documents)
        .scalar_subquery()
    )
    order_docs = (
        select(documents, file_version)
        .join(Order, Order.id == documents.order_id)
        .outerjoin(Customer, Customer.id == Order.customer_id)
        .where(*filters)
    )
    total = await session.scalar(
        order_docs.with_only_columns(func.count(documents.id), maintain_column_froms=True)
    )
    rows = (await session.execute(
        order_docs
        .order_by(documents.created_at.desc(), documents.id.desc())
        .offset(inputs.offset)
        .limit(inputs.limit)
    )).all()
    artifacts_by_document = defaultdict(list)
    if rows:
        artifact = DocumentArtifact
        revisions = await session.execute(select(
            artifact.order_document_id,
            artifact.id,
            artifact.checksum_sha256,
            artifact.is_authoritative,
        ).where(
            artifact.tenant_id == scope.tenant_id,
            artifact.order_document_id.in_([document.id for document, _ in rows]),
        ))
        for revision in revisions:
            artifacts_by_document[revision.order_document_id].append(revision)
    return rows, total, artifacts_by_document
