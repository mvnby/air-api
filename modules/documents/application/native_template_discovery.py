"""Discover a server-approved placeholder contract in a native DOCX."""

from __future__ import annotations

from typing import Mapping

from modules.documents.domain.placeholder_catalog import MAINTENANCE_OBSERVATION_ROW_PLACEHOLDERS
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

_TABLE_CATALOGS = {
    "observations": MAINTENANCE_OBSERVATION_ROW_PLACEHOLDERS,
    "lines": LINE_ROW_PLACEHOLDERS,
    "payment_schedule": PAYMENT_SCHEDULE_ROW_PLACEHOLDERS,
}


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

    table_blocks = tuple(
        TableBlockSpec(
            name=table_name,
            row_fields=frozenset(item.name for item in row_placeholders),
        )
        for table_name, row_placeholders in _TABLE_CATALOGS.items()
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


def resolve_native_placeholder_contract(
    content: bytes, persisted_schema: Mapping[str, object]
) -> NativeTemplatePlaceholderContract:
    """Recover old SDT omissions without changing an immutable stored version.

    Only newly visible identifiers from content controls can extend the saved
    contract, and only through the same server-owned catalogue as an upload.
    Unknown fields still fail renderer validation. Ordinary source fields never
    widen an explicitly narrowed version contract.
    """
    omitted_fields, omitted_conditions = (
        NativeDocxRenderer().discover_content_control_omissions(content)
    )
    fields = set(persisted_schema.get("fields", []))
    conditions = set(persisted_schema.get("conditions", []))
    fields.update(item.name for item in SCALAR_PLACEHOLDERS if item.name in omitted_fields)
    conditions.update(
        item.name for item in CONDITIONAL_FLAGS if item.name in omitted_conditions
    )
    blocks = {
        str(item["name"]): TableBlockSpec(
            name=str(item["name"]), row_fields=frozenset(item.get("row_fields", []))
        )
        for item in persisted_schema.get("tables", [])
    }
    for name, descriptors in _TABLE_CATALOGS.items():
        row_fields = frozenset(item.name for item in descriptors)
        recovered = row_fields & omitted_fields
        if name in blocks:
            block = blocks[name]
            blocks[name] = TableBlockSpec(name=name, row_fields=block.row_fields | recovered)
        elif name in omitted_fields or recovered:
            blocks[name] = TableBlockSpec(name=name, row_fields=row_fields)
    return NativeTemplatePlaceholderContract.create(
        field_catalog=fields, condition_catalog=conditions, table_blocks=blocks.values()
    )
