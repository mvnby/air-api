from dataclasses import replace

import pytest

from modules.documents.infrastructure.artifact_storage import (
    PrivateDocumentArtifactStorage,
)
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.mark.asyncio
async def test_document_artifacts_are_isolated_by_tenant_and_document(tmp_path):
    underlying = LocalPrivateAttachmentStorage(tmp_path)
    storage = PrivateDocumentArtifactStorage(underlying)

    first = await storage.save(
        tenant_id=7,
        document_id=11,
        kind="rendered_docx",
        filename="Договор № 11.docx",
        content_type=DOCX_MIME,
        content=b"same document bytes",
    )
    second = await storage.save(
        tenant_id=8,
        document_id=11,
        kind="rendered_docx",
        filename="Договор № 11.docx",
        content_type=DOCX_MIME,
        content=b"same document bytes",
    )

    assert first.storage_key != second.storage_key
    assert "documents-tenant-7-document-11-rendered-docx.docx" in first.storage_key
    assert await storage.read(first) == b"same document bytes"
    with pytest.raises(ValueError, match="tenant/document scope"):
        await storage.read(replace(first, tenant_id=8))


@pytest.mark.asyncio
async def test_document_artifact_readback_checks_hash_and_local_presign_is_none(
    tmp_path,
):
    underlying = LocalPrivateAttachmentStorage(tmp_path)
    storage = PrivateDocumentArtifactStorage(underlying)
    artifact = await storage.save(
        tenant_id=7,
        document_id=12,
        kind="pdf",
        filename="Акт-12.pdf",
        content_type="application/pdf",
        content=b"immutable pdf bytes",
    )

    assert artifact.checksum_sha256
    assert await storage.read(artifact) == b"immutable pdf bytes"
    assert await storage.presign(artifact, expires_seconds=300) is None

    (tmp_path / artifact.storage_key).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        await storage.read(artifact)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tenant_id", "document_id"),
    [(0, 1), (1, 0), (-1, 1), (True, 1)],
)
async def test_document_artifact_rejects_invalid_scope_ids(
    tmp_path, tenant_id, document_id
):
    storage = PrivateDocumentArtifactStorage(LocalPrivateAttachmentStorage(tmp_path))

    with pytest.raises(ValueError, match="positive integer"):
        await storage.save(
            tenant_id=tenant_id,
            document_id=document_id,
            kind="pdf",
            filename="акт.pdf",
            content_type="application/pdf",
            content=b"pdf",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "filename", "content_type"),
    [
        ("unknown", "document.pdf", "application/pdf"),
        ("pdf", "document.docx", "application/pdf"),
        ("pdf", "../../document.pdf", "application/pdf"),
        ("pdf", 'document".pdf', "application/pdf"),
        ("pdf", "document.pdf", "text/plain"),
    ],
)
async def test_document_artifact_rejects_unknown_kind_or_unsafe_metadata(
    tmp_path,
    kind,
    filename,
    content_type,
):
    storage = PrivateDocumentArtifactStorage(LocalPrivateAttachmentStorage(tmp_path))

    with pytest.raises(ValueError):
        await storage.save(
            tenant_id=1,
            document_id=2,
            kind=kind,
            filename=filename,
            content_type=content_type,
            content=b"content",
        )
