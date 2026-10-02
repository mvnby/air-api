"""Compatibility exports for document HTTP payloads; definitions are import-safe."""
from schemas_business_document_terms import (
    ActTermsPayload,
    BusinessDocumentTermsPayload,
    PaymentScheduleItemPayload,
)

__all__ = ["ActTermsPayload", "BusinessDocumentTermsPayload", "PaymentScheduleItemPayload"]
