"""Discover a server-approved placeholder contract in a native DOCX."""

from __future__ import annotations

from modules.documents.domain import (
    CONDITIONAL_FLAGS,
    LINE_ROW_PLACEHOLDERS,
    PAYMENT_SCHEDULE_ROW_PLACEHOLDERS,
    SCALAR_PLACEHOLDERS,
)
from modules.documents.infrastructure.renderers import NativeDocxRenderer, TableBlockSpec

from .template_versions import (
    NativeTemplatePlaceholderContract,
    TemplateVersionError,
    preflight_native_docx,
)


def discover_native_placeholder_contract(
    content: bytes,
) -> NativeTemplatePlaceholderContract:
    """Build the narrow allowlisted contract discovered in a DOCX source."""

    preflight_native_docx(content)
    renderer = NativeDocxRenderer()
    try:
        discovered = renderer.discover_placeholders(content)
        discovered_conditions = renderer.discover_conditions(content)
    except ValueError as exc:
        raise TemplateVersionError(str(exc)) from exc

    table_catalogs = {
        "lines": LINE_ROW_PLACEHOLDERS,
        "payment_schedule": PAYMENT_SCHEDULE_ROW_PLACEHOLDERS,
    }
    table_blocks = tuple(
        TableBlockSpec(
            name=table_name,
            row_fields=frozenset(item.name for item in row_placeholders),
        )
        for table_name, row_placeholders in table_catalogs.items()
        if table_name in discovered
        or any(item.name in discovered for item in row_placeholders)
    )
    return NativeTemplatePlaceholderContract.create(
        field_catalog=(
            item.name for item in SCALAR_PLACEHOLDERS if item.name in discovered
        ),
        condition_catalog=(
            item.name
            for item in CONDITIONAL_FLAGS
            if item.name in discovered_conditions
        ),
        table_blocks=table_blocks,
    )
