"""Provider-neutral document rendering contracts and adapters."""

from .contracts import (
    DocumentTemplateVersion,
    RenderContext,
    RenderedDocx,
    TableBlockSpec,
    TemplateValidationError,
    TemplateValidationResult,
)
from .docx_renderer import ContextFieldError, NativeDocxRenderer
from .pdf import (
    GotenbergPdfConverter,
    PdfConversionError,
    PdfConversionUnavailableError,
    PdfConverter,
    PdfConverterHealth,
    UnavailablePdfConverter,
)

__all__ = [
    "ContextFieldError",
    "DocumentTemplateVersion",
    "GotenbergPdfConverter",
    "NativeDocxRenderer",
    "PdfConversionError",
    "PdfConversionUnavailableError",
    "PdfConverter",
    "PdfConverterHealth",
    "RenderContext",
    "RenderedDocx",
    "TableBlockSpec",
    "TemplateValidationError",
    "TemplateValidationResult",
    "UnavailablePdfConverter",
]
