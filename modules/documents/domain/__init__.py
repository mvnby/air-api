from .lifecycle import (
    DocumentLifecycleError,
    DocumentLifecycleState,
    DocumentStatus,
    transition_document,
)
from .numbering import (
    DEFAULT_NUMBER_POLICIES,
    DocumentNumberScope,
    EffectiveDocumentNumberPolicy,
    new_internal_reference,
    numbering_policy_key,
)
from .placeholder_catalog import (
    CONDITIONAL_FLAGS,
    LINE_ROW_PLACEHOLDERS,
    SCALAR_PLACEHOLDERS,
    SUPPORTED_NATIVE_DOCUMENT_TYPES,
    ConditionDescriptor,
    PlaceholderDescriptor,
)
from .consumer_terms import (
    B2C_NATIVE_DOCUMENT_TYPES,
    ConsumerDocumentTerms,
    DEFAULT_GOODS_WARRANTY_MONTHS,
)

__all__ = [
    "DocumentLifecycleError",
    "DocumentLifecycleState",
    "DocumentNumberScope",
    "EffectiveDocumentNumberPolicy",
    "DEFAULT_NUMBER_POLICIES",
    "DocumentStatus",
    "new_internal_reference",
    "numbering_policy_key",
    "CONDITIONAL_FLAGS",
    "LINE_ROW_PLACEHOLDERS",
    "SCALAR_PLACEHOLDERS",
    "SUPPORTED_NATIVE_DOCUMENT_TYPES",
    "ConditionDescriptor",
    "B2C_NATIVE_DOCUMENT_TYPES",
    "ConsumerDocumentTerms",
    "DEFAULT_GOODS_WARRANTY_MONTHS",
    "PlaceholderDescriptor",
    "transition_document",
]
