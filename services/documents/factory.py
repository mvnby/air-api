from sqlalchemy.ext.asyncio import AsyncSession
from services.documents.base import BaseDocumentStrategy, TEMPLATES
from services.documents.standard import (
    B2CDocumentStrategy,
    WorkOrderStrategy,
    ActStrategy,
    DefectActStrategy,
    GeneralDocStrategy,
    WarrantyCertificateStrategy,
)
from services.documents.logistics import LogisticsSheetStrategy

class DocumentFactory:
    @staticmethod
    def get_strategy(doc_type: str, session: AsyncSession, order_id: int) -> BaseDocumentStrategy:
        if doc_type not in TEMPLATES:
            raise ValueError(f"Unknown document type: {doc_type}")

        if doc_type == "work_order":
            return WorkOrderStrategy(session, order_id)
        elif doc_type == "act":
            return ActStrategy(session, order_id)
        elif doc_type == "defect_act":
            return DefectActStrategy(session, order_id)
        elif doc_type in ["tn2", "ttn1"]:
            return LogisticsSheetStrategy(session, order_id)
        elif doc_type in ["retail_receipt", "service_act", "maintenance_service_act"]:
            return B2CDocumentStrategy(session, order_id)
        elif doc_type == "warranty_certificate":
            return WarrantyCertificateStrategy(session, order_id)
        elif doc_type in ["contract", "offer", "invoice"]:
            return GeneralDocStrategy(session, order_id)
        else:
            # Default to General for any new unexpected types that exist in TEMPLATES
            return GeneralDocStrategy(session, order_id)
