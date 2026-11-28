from core.config import settings
from modules.documents.infrastructure.renderers import GotenbergPdfConverter, UnavailablePdfConverter


def configured_pdf_converter():
    url = str(settings.DOCUMENT_PDF_CONVERTER_URL or "").strip()
    if not url:
        return UnavailablePdfConverter("PDF-конвертер для нативных документов не настроен")
    return GotenbergPdfConverter(url, timeout_seconds=float(settings.DOCUMENT_PDF_CONVERTER_TIMEOUT_SECONDS))
