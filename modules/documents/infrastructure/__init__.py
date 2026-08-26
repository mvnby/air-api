"""Infrastructure adapters for the documents module."""

from .numbering_repository import (
    DocumentNumberReservationResult,
    DocumentNumberingRepository,
)
from .template_source_storage import (
    PrivateTemplateSourceStorage,
    StoredTemplateSource,
    TemplateSourceStorage,
)

__all__ = [
    "DocumentNumberReservationResult",
    "DocumentNumberingRepository",
    "PrivateTemplateSourceStorage",
    "StoredTemplateSource",
    "TemplateSourceStorage",
]
