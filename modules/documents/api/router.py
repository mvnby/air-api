"""Compatibility composition point for the modular manager document API.

Existing callers import ``modules.documents.api.router.router``. Keep that
public surface stable while each focused router owns one document concern.
The two factory names remain here intentionally: integration tests and runtime
overrides patch them at this historic import path.
"""

from fastapi import APIRouter

from core.config import settings
from modules.documents.infrastructure.renderers import (
    GotenbergPdfConverter,
    UnavailablePdfConverter,
)
from services.private_attachment_storage_service import get_private_attachment_storage

from . import (
    legal_entities_number_policies,
    managed_documents_artifacts,
    templates_runtime,
)


def _pdf_converter():
    url = str(settings.DOCUMENT_PDF_CONVERTER_URL or "").strip()
    if not url:
        return UnavailablePdfConverter(
            "PDF-конвертер для нативных документов не настроен"
        )
    return GotenbergPdfConverter(
        url,
        timeout_seconds=float(settings.DOCUMENT_PDF_CONVERTER_TIMEOUT_SECONDS),
    )


router = APIRouter()
router.include_router(legal_entities_number_policies.router)
router.include_router(templates_runtime.router)
router.include_router(managed_documents_artifacts.router)


__all__ = ["router", "get_private_attachment_storage", "_pdf_converter"]
