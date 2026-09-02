"""Official identity and artifact generation for managed documents."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import date

from modules.documents.infrastructure.artifact_storage import (
    DocumentArtifactStorage,
    StoredDocumentArtifact,
)
from modules.documents.infrastructure.renderers import NativeDocxRenderer, PdfConverter
from modules.documents.infrastructure.template_source_storage import TemplateSourceStorage

from .artifact_helpers import artifact_basename, build_render_inputs
from .editable_draft import finalize_editable_draft


DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
PDF_CONTENT_TYPE = "application/pdf"


def assign_official_identity(
    *, document, policy, reservation, period_key: str, issued_on: date
) -> tuple[dict, dict]:
    """Apply one reserved official identity to the persisted render snapshot."""

    official_number = f"{reservation.number_value:0{policy.minimum_width}d}"
    snapshot = deepcopy(document.render_snapshot)
    values = snapshot.setdefault("values", {})
    values.update(
        {
            "document.internal_reference": document.internal_reference,
            "document.official_series": policy.series,
            "document.official_number": official_number,
            "document.official_full_number": reservation.number_text,
            "document.issued_on": issued_on.strftime("%d.%m.%Y"),
            "document.act_sequence_number": str(reservation.number_value),
        }
    )
    document.official_series = policy.series
    document.official_period_key = period_key
    document.official_number = official_number
    document.official_date = issued_on
    document.render_snapshot = snapshot
    return snapshot, values


async def render_and_store_issued_artifacts(
    *,
    tenant_id: int,
    document_id: int,
    document_type: str,
    official_full_number: str,
    template,
    version,
    snapshot: dict,
    official_values: dict,
    editable_source: bytes | None,
    required_placeholder_counts: dict[str, int] | None,
    template_storage: TemplateSourceStorage,
    artifact_storage: DocumentArtifactStorage,
    pdf_converter: PdfConverter,
) -> tuple[StoredDocumentArtifact, StoredDocumentArtifact]:
    """Render final DOCX/PDF bytes and persist them through immutable storage."""

    if editable_source is not None:
        rendered_content = finalize_editable_draft(
            source=editable_source,
            placeholder_schema=version.placeholder_schema or {},
            official_values=official_values,
            required_placeholder_counts=required_placeholder_counts,
        )
    else:
        source = await template_storage.read_persisted(
            tenant_id=tenant_id,
            template_id=int(template.id),
            version=version.version,
            storage_key=version.source_storage_key,
            filename=str(version.source_filename or "template.docx"),
            checksum_sha256=version.checksum_sha256,
        )
        render_template, render_context = build_render_inputs(
            template=template,
            version=version,
            source=source,
            snapshot=snapshot,
        )
        rendered_content = NativeDocxRenderer().render(
            render_template, render_context
        ).content

    basename = artifact_basename(document_type, official_full_number)
    pdf_content = await asyncio.to_thread(
        pdf_converter.convert_docx,
        rendered_content,
        filename=f"{basename}.docx",
    )
    stored_docx = await artifact_storage.save(
        tenant_id=tenant_id,
        document_id=document_id,
        kind="rendered_docx",
        filename=f"{basename}.docx",
        content_type=DOCX_CONTENT_TYPE,
        content=rendered_content,
    )
    stored_pdf = await artifact_storage.save(
        tenant_id=tenant_id,
        document_id=document_id,
        kind="pdf",
        filename=f"{basename}.pdf",
        content_type=PDF_CONTENT_TYPE,
        content=pdf_content,
    )
    return stored_docx, stored_pdf
