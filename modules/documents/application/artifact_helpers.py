"""Pure rendering and persisted-artifact helpers for managed documents."""

from __future__ import annotations

import re
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import DocumentArtifact, DocumentTemplate, DocumentTemplateVersion
from modules.documents.infrastructure.artifact_storage import StoredDocumentArtifact
from modules.documents.infrastructure.renderers import (
    DocumentTemplateVersion as RenderTemplateVersion,
    RenderContext,
    TableBlockSpec,
)


def build_render_inputs(
    *,
    template: DocumentTemplate,
    version: DocumentTemplateVersion,
    source: bytes,
    snapshot: dict[str, Any],
) -> tuple[RenderTemplateVersion, RenderContext]:
    schema = version.placeholder_schema or {}
    field_catalog = frozenset(str(value) for value in schema.get("fields", []))
    condition_catalog = frozenset(str(value) for value in schema.get("conditions", []))
    table_blocks = tuple(
        TableBlockSpec(
            name=str(item.get("name", "")),
            row_fields=frozenset(str(value) for value in item.get("row_fields", [])),
        )
        for item in schema.get("tables", [])
    )
    render_template = RenderTemplateVersion(
        template_key=f"template-{template.id}",
        version=version.version,
        source=source,
        field_catalog=field_catalog,
        condition_catalog=condition_catalog,
        table_blocks=table_blocks,
        filename=str(version.source_filename or "template.docx"),
    )
    snapshot_values = snapshot.get("values", {})
    snapshot_conditions = snapshot.get("conditions")
    snapshot_tables = snapshot.get("table_rows", {})
    context = RenderContext(
        values={field: snapshot_values.get(field, "") for field in field_catalog},
        conditions=_condition_values(condition_catalog, snapshot_conditions),
        table_rows={
            block.name: tuple(
                {field: row.get(field, "") for field in block.row_fields}
                for row in snapshot_tables.get(block.name, [])
            )
            for block in table_blocks
        },
    )
    return render_template, context


def _condition_values(
    condition_catalog: frozenset[str],
    snapshot_conditions: Any,
) -> dict[str, bool]:
    if not condition_catalog:
        return {}
    if not isinstance(snapshot_conditions, Mapping):
        raise ValueError("Снимок документа не содержит каталог условных флагов")

    missing = condition_catalog - set(snapshot_conditions)
    if missing:
        raise ValueError(
            "В снимке документа отсутствуют условные флаги: "
            + ", ".join(sorted(missing))
        )

    values: dict[str, bool] = {}
    for condition in condition_catalog:
        value = snapshot_conditions[condition]
        if not isinstance(value, bool):
            raise TypeError(
                f"Условный флаг {condition!r} в снимке документа должен быть boolean"
            )
        values[condition] = value
    return values


def artifact_basename(document_type: str, official_full_number: str) -> str:
    safe_number = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._-]+", "-", official_full_number).strip(
        "-."
    )
    return f"{document_type}-{safe_number or 'document'}"[:220]


def artifact_row(stored: StoredDocumentArtifact) -> DocumentArtifact:
    return DocumentArtifact(
        tenant_id=stored.tenant_id,
        order_document_id=stored.document_id,
        kind=stored.kind,
        provider=stored.provider,
        storage_key=stored.storage_key,
        content_type=stored.content_type,
        filename=stored.filename,
        checksum_sha256=stored.checksum_sha256,
        size_bytes=stored.size_bytes,
        is_authoritative=True,
    )


def stored_artifact(artifact: DocumentArtifact) -> StoredDocumentArtifact:
    return StoredDocumentArtifact(
        tenant_id=artifact.tenant_id,
        document_id=artifact.order_document_id,
        kind=artifact.kind,
        provider=artifact.provider,
        storage_key=artifact.storage_key,
        content_type=artifact.content_type,
        filename=artifact.filename,
        checksum_sha256=artifact.checksum_sha256,
        size_bytes=artifact.size_bytes,
    )


async def list_artifacts(
    session: AsyncSession,
    tenant_id: int,
    document_id: int,
) -> list[DocumentArtifact]:
    return list(
        (
            await session.execute(
                select(DocumentArtifact)
                .where(
                    DocumentArtifact.tenant_id == tenant_id,
                    DocumentArtifact.order_document_id == document_id,
                    DocumentArtifact.is_authoritative.is_(True),
                )
                .order_by(DocumentArtifact.kind)
            )
        )
        .scalars()
        .all()
    )
