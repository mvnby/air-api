"""Shared transport conversion for native draft creation and read-only checks."""

from modules.documents.application.context_builder import DocumentContextSelection
from .schemas import ManagedDocumentDraftPayload
from modules.documents.domain import (
    ActTerms,
    BusinessDocumentTerms,
    ConsumerDocumentTerms,
    PaymentScheduleItem,
    TransportTerms,
)


def selection_from_payload(order_id: int, payload: ManagedDocumentDraftPayload) -> DocumentContextSelection:
    return DocumentContextSelection(
        order_id=order_id,
        document_type=payload.document_type,
        legal_entity_id=payload.legal_entity_id,
        issue_date=payload.issue_date,
        issue_city=payload.issue_city,
        proposal_id=payload.proposal_id,
        base_document_id=payload.base_document_id,
        base_customer_contract_id=payload.base_customer_contract_id,
        scope_customer_branch_id=payload.scope_customer_branch_id,
        scope_title=payload.scope_title,
        scope_address=payload.scope_address,
        scope_service_line_ids=tuple(payload.scope_service_line_ids),
        scope_service_line_quantities=payload.scope_service_line_quantities,
        scope_product_line_ids=tuple(payload.scope_product_line_ids),
        business_role=payload.business_role,
        document_role_type=payload.document_role_type,
        consumer_terms=(
            ConsumerDocumentTerms(**payload.consumer_terms.model_dump())
            if payload.consumer_terms is not None
            else None
        ),
        business_terms=(
            BusinessDocumentTerms(
                **{
                    **payload.business_terms.model_dump(exclude={"payment_schedule"}),
                    "payment_schedule": tuple(
                        PaymentScheduleItem(**item.model_dump())
                        for item in payload.business_terms.payment_schedule
                    ),
                }
            )
            if payload.business_terms is not None
            else None
        ),
        act_terms=(
            ActTerms(**payload.act_terms.model_dump())
            if payload.act_terms is not None
            else None
        ),
        transport_terms=(
            TransportTerms(**payload.transport_terms.model_dump())
            if payload.transport_terms is not None
            else None
        ),
    )
