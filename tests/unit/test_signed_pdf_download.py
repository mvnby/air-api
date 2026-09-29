from io import BytesIO

import pytest

from modules.documents.application.native_download import native_document_pdf_download


@pytest.mark.asyncio
async def test_native_download_prefers_signed_pdf(monkeypatch):
    class Artifact:
        def __init__(self, kind, filename):
            self.kind = kind
            self.filename = filename
            self.provider = "local"

    original = Artifact("pdf", "original.pdf")
    signed = Artifact("signed_pdf", "signed.pdf")

    async def list_artifacts(*_args, **_kwargs):
        return [original, signed]

    class Storage:
        async def read(self, artifact):
            return b"signed" if artifact.kind == "signed_pdf" else b"original"

    monkeypatch.setattr(
        "modules.documents.application.native_download.ManagedDocumentService.list_artifacts",
        list_artifacts,
    )
    monkeypatch.setattr(
        "modules.documents.application.native_download.ManagedDocumentService.stored_artifact",
        lambda artifact: artifact,
    )
    monkeypatch.setattr(
        "modules.documents.application.native_download.PrivateDocumentArtifactStorage",
        lambda _storage: Storage(),
    )
    monkeypatch.setattr(
        "modules.documents.application.native_download.private_attachment_storage_service.get_private_attachment_storage",
        lambda _provider: object(),
    )

    stream, filename = await native_document_pdf_download(
        None,
        tenant_scope=type("Scope", (), {"tenant_id": 1})(),
        document=type("Document", (), {"id": 4})(),
    )

    assert isinstance(stream, BytesIO)
    assert stream.getvalue() == b"signed"
    assert filename == "signed.pdf"
