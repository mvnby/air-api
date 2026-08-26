"""Application services for the modular document subsystem."""

from .legal_entities import DocumentLegalEntityService
from .template_versions import (
    NativeTemplatePlaceholderContract,
    NativeTemplateVersionService,
    TemplateVersionConflictError,
    TemplateVersionError,
    TemplateVersionNotFoundError,
    TemplateVersionValidationError,
)
from .context_builder import (
    DocumentContextBuilder,
    DocumentContextError,
    DocumentContextSelection,
)
from .number_policies import (
    DocumentNumberPolicyError,
    DocumentNumberPolicyNotFoundError,
    DocumentNumberPolicyService,
    EffectivePolicyItem,
)
from .errors import (
    ManagedDocumentConflictError,
    ManagedDocumentError,
    ManagedDocumentGenerationError,
    ManagedDocumentNotFoundError,
)
from .lifecycle_service import IssuedDocumentResult, ManagedDocumentService

__all__ = [
    "DocumentContextBuilder",
    "DocumentContextError",
    "DocumentContextSelection",
    "DocumentLegalEntityService",
    "DocumentNumberPolicyError",
    "DocumentNumberPolicyNotFoundError",
    "DocumentNumberPolicyService",
    "EffectivePolicyItem",
    "IssuedDocumentResult",
    "ManagedDocumentConflictError",
    "ManagedDocumentError",
    "ManagedDocumentGenerationError",
    "ManagedDocumentNotFoundError",
    "ManagedDocumentService",
    "NativeTemplatePlaceholderContract",
    "NativeTemplateVersionService",
    "TemplateVersionConflictError",
    "TemplateVersionError",
    "TemplateVersionNotFoundError",
    "TemplateVersionValidationError",
]
