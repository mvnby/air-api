"""On-demand preview rendering for unissued managed documents."""

from __future__ import annotations

import asyncio
from copy import deepcopy

from sqlalchemy.ext.asyncio import AsyncSession

from models.tenancy import TenantScope
from modules.documents.domain import DocumentStatus
from modules.documents.infrastructure.artifact_storage import DocumentArtifactStorage
from modules.documents.infrastructure.renderers import NativeDocxRenderer, PdfConverter
from modules.documents.infrastructure.template_source_storage import TemplateSourceStorage

from .artifact_helpers import build_render_inputs, stored_artifact
from .editable_draft import (
    DEFERRED_OFFICIAL_FIELDS,
    finalize_editable_draft,
    preview_values,
)
from .errors import ManagedDocumentConflictError
from .lifecycle_service import ManagedDocumentService
from .template_selection import load_document_template_version


class ManagedDocumentDraftPreviewService:
    @classmethod
    async def render_pdf(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document_id: int,
        template_storage: TemplateSourceStorage,
        artifact_storage: DocumentArtifactStorage,
        pdf_converter: PdfConverter,
    ) -> tuple[bytes, str]:
        document = await ManagedDocumentService.get_document(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
        )
        if document.status != DocumentStatus.DRAFT.value:
            raise ManagedDocumentConflictError(
                "Предпросмотр черновика доступен только до выпуска"
            )
        if not document.render_snapshot or not document.template_version_id:
            raise ManagedDocumentConflictError(
                "Черновик не относится к нативному документному контуру"
            )
        template, version = await load_document_template_version(
            session,
            tenant_scope=tenant_scope,
            document=document,
        )
        schema = version.placeholder_schema or {}
        deferred = frozenset(str(item) for item in schema.get("fields", [])) & DEFERRED_OFFICIAL_FIELDS
        displayed_values = preview_values(deferred)
        artifacts = await ManagedDocumentService.list_artifacts(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
        )
        source_artifact = next(
            (item for item in artifacts if item.kind == "source_docx"),
            None,
        )
        if source_artifact is not None:
            editable = await artifact_storage.read(stored_artifact(source_artifact))
            rendered_docx = finalize_editable_draft(
                source=editable,
                placeholder_schema=schema,
                official_values=displayed_values,
            )
        else:
            source = await template_storage.read_persisted(
                tenant_id=tenant_scope.tenant_id,
                template_id=int(template.id),
                version=version.version,
                storage_key=version.source_storage_key,
                filename=str(version.source_filename or "template.docx"),
                checksum_sha256=version.checksum_sha256,
            )
            snapshot = deepcopy(document.render_snapshot)
            snapshot.setdefault("values", {}).update(displayed_values)
            render_template, render_context = build_render_inputs(
                template=template,
                version=version,
                source=source,
                snapshot=snapshot,
            )
            rendered_docx = NativeDocxRenderer().render(
                render_template, render_context
            ).content
        filename = f"draft-{document.internal_reference or document.id}.docx"
        pdf = await asyncio.to_thread(
            pdf_converter.convert_docx,
            rendered_docx,
            filename=filename,
        )
        return pdf, filename.removesuffix(".docx") + ".pdf"
