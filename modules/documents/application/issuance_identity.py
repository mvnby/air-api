"""Claim an official identity once and verify it when issuance resumes."""

from sqlmodel import select

from models import DocumentLegalEntity, DocumentNumberReservation
from modules.documents.domain import DocumentNumberScope, numbering_policy_key
from modules.documents.domain.numbering import google_number_history_type
from modules.documents.infrastructure.numbering_repository import DocumentNumberingRepository

from .errors import ManagedDocumentConflictError
from .issuance_artifacts import assign_official_identity
from .number_policies import DocumentNumberPolicyService


async def reserve_official_identity(session, *, document, tenant_scope, issued_on):
    tenant_id = tenant_scope.tenant_id
    if document.official_number is not None:
        reservation = await session.scalar(select(DocumentNumberReservation).where(
            DocumentNumberReservation.tenant_id == tenant_id,
            DocumentNumberReservation.document_id == document.id,
            DocumentNumberReservation.status == "reserved",
        ).with_for_update())
        values = document.render_snapshot["values"]
        if (reservation is None or reservation.series != document.official_series
                or reservation.period_key != document.official_period_key
                or reservation.number_text != values.get("document.official_full_number")
                or values.get("document.official_number") != document.official_number):
            raise ManagedDocumentConflictError("Не удалось подтвердить зарезервированный номер документа")
        return reservation.number_text

    policy = await DocumentNumberPolicyService.get_effective(
        session, tenant_scope=tenant_scope, legal_entity_id=document.legal_entity_id,
        policy_key=numbering_policy_key(document.doc_type, document.business_role),
    )
    basis_key = None
    if document.base_document_id:
        basis_key = f"document-{document.base_document_id}"
    elif document.base_customer_contract_id:
        basis_key = f"contract-{document.base_customer_contract_id}"
    period_key = policy.period_key(issued_on, basis_key=basis_key)
    legacy_document_type = None
    if policy.period_mode == "calendar_year" and await session.scalar(
        select(DocumentLegalEntity.id).where(
            DocumentLegalEntity.id == document.legal_entity_id,
            DocumentLegalEntity.tenant_id == tenant_id,
            DocumentLegalEntity.is_default.is_(True),
        )
    ):
        legacy_document_type = google_number_history_type(document.doc_type, policy.series)
    reservation = await DocumentNumberingRepository.reserve(
        session,
        scope=DocumentNumberScope(tenant_id, document.legal_entity_id, policy.document_type, policy.series, period_key),
        idempotency_key=f"issue:{document.internal_reference}",
        minimum_width=policy.minimum_width,
        number_text_formatter=lambda value: policy.format_number_text(period_key, value),
        legacy_document_type=legacy_document_type,
    )
    await DocumentNumberingRepository.attach_to_document(
        session, tenant_id=tenant_id, reservation_id=reservation.reservation_id, document_id=document.id,
    )
    assign_official_identity(
        document=document, policy=policy, reservation=reservation, period_key=period_key, issued_on=issued_on,
    )
    return reservation.number_text
