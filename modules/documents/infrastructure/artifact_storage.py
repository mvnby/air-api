"""Private, provider-neutral persistence for immutable document artifacts.

This adapter deliberately sits above the generic private attachment storage.
It gives documents their own variant namespace and makes every read or
presigned download prove the tenant/document boundary again.  The application
layer can persist :class:`StoredDocumentArtifact` fields in ``DocumentArtifact``
without acquiring a dependency on an S3/R2/local implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePath
from typing import Protocol
import unicodedata

from services.private_attachment_storage_service import (
    PrivateAttachmentStorage,
    VariantScopedPrivateAttachmentStorage,
)


DOCUMENT_ARTIFACT_KINDS = frozenset({"source_docx", "rendered_docx", "pdf"})

_KIND_FORMATS: dict[str, tuple[str, str]] = {
    "source_docx": (
        ".docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "rendered_docx": (
        ".docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "pdf": (".pdf", "application/pdf"),
}
_MAX_FILENAME_LENGTH = 255


@dataclass(frozen=True, slots=True)
class StoredDocumentArtifact:
    """Storage metadata safe to persist in the document-artifact registry."""

    tenant_id: int
    document_id: int
    kind: str
    provider: str
    storage_key: str
    content_type: str
    filename: str
    checksum_sha256: str
    size_bytes: int


class DocumentArtifactStorage(Protocol):
    """Provider-neutral storage boundary used by the documents application layer."""

    provider_name: str

    async def save(
        self,
        *,
        tenant_id: int,
        document_id: int,
        kind: str,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> StoredDocumentArtifact: ...

    async def read(self, artifact: StoredDocumentArtifact) -> bytes: ...

    async def presign(
        self,
        artifact: StoredDocumentArtifact,
        *,
        expires_seconds: int,
    ) -> str | None: ...


class PrivateDocumentArtifactStorage:
    """Document-scoped adapter over the existing private R2/S3/local storage."""

    def __init__(self, storage: PrivateAttachmentStorage) -> None:
        self._storage = VariantScopedPrivateAttachmentStorage(
            storage,
            variant_scope="documents",
        )
        self.provider_name = storage.provider_name

    async def save(
        self,
        *,
        tenant_id: int,
        document_id: int,
        kind: str,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> StoredDocumentArtifact:
        normalized = _validate_metadata(
            tenant_id=tenant_id,
            document_id=document_id,
            kind=kind,
            filename=filename,
            content_type=content_type,
        )
        if not isinstance(content, bytes) or not content:
            raise ValueError("Document artifact content must be non-empty bytes")

        checksum = sha256(content).hexdigest()
        stored = await self._storage.save(
            content=content,
            content_hash=checksum,
            extension=normalized.extension.lstrip("."),
            content_type=normalized.content_type,
            variant=_variant_for(
                tenant_id=normalized.tenant_id,
                document_id=normalized.document_id,
                kind=normalized.kind,
            ),
        )
        return StoredDocumentArtifact(
            tenant_id=normalized.tenant_id,
            document_id=normalized.document_id,
            kind=normalized.kind,
            provider=stored.provider,
            storage_key=stored.storage_key,
            content_type=normalized.content_type,
            filename=normalized.filename,
            checksum_sha256=checksum,
            size_bytes=len(content),
        )

    async def read(self, artifact: StoredDocumentArtifact) -> bytes:
        normalized = _validate_artifact(artifact, expected_provider=self.provider_name)
        content = await self._storage.read(normalized.storage_key)
        actual_checksum = sha256(content).hexdigest()
        if actual_checksum != normalized.checksum_sha256:
            raise ValueError("Document artifact SHA-256 verification failed")
        if len(content) != normalized.size_bytes:
            raise ValueError("Document artifact size verification failed")
        return content

    async def presign(
        self,
        artifact: StoredDocumentArtifact,
        *,
        expires_seconds: int,
    ) -> str | None:
        normalized = _validate_artifact(artifact, expected_provider=self.provider_name)
        return await self._storage.presign(
            normalized.storage_key,
            expires_seconds=expires_seconds,
            download_name=normalized.filename,
        )


@dataclass(frozen=True, slots=True)
class _ValidatedMetadata:
    tenant_id: int
    document_id: int
    kind: str
    filename: str
    content_type: str
    extension: str


def _validate_artifact(
    artifact: StoredDocumentArtifact,
    *,
    expected_provider: str,
) -> StoredDocumentArtifact:
    if not isinstance(artifact, StoredDocumentArtifact):
        raise TypeError("artifact must be StoredDocumentArtifact")
    metadata = _validate_metadata(
        tenant_id=artifact.tenant_id,
        document_id=artifact.document_id,
        kind=artifact.kind,
        filename=artifact.filename,
        content_type=artifact.content_type,
    )
    if artifact.provider != expected_provider:
        raise ValueError("Document artifact belongs to another storage provider")
    if not _is_sha256(artifact.checksum_sha256):
        raise ValueError("Document artifact checksum must be a SHA-256 digest")
    if (
        not isinstance(artifact.size_bytes, int)
        or isinstance(artifact.size_bytes, bool)
        or artifact.size_bytes < 1
    ):
        raise ValueError("Document artifact size must be positive")
    storage_key = str(artifact.storage_key or "").strip()
    expected_filename = (
        f"documents-tenant-{metadata.tenant_id}-document-{metadata.document_id}-"
        f"{metadata.kind.replace('_', '-')}{metadata.extension}"
    )
    if not storage_key or not storage_key.endswith(f"/{expected_filename}"):
        raise ValueError(
            "Document artifact storage key is outside its tenant/document scope"
        )
    return artifact


def _validate_metadata(
    *,
    tenant_id: int,
    document_id: int,
    kind: str,
    filename: str,
    content_type: str,
) -> _ValidatedMetadata:
    normalized_tenant_id = _positive_id(tenant_id, "tenant_id")
    normalized_document_id = _positive_id(document_id, "document_id")
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind not in DOCUMENT_ARTIFACT_KINDS:
        raise ValueError("Unsupported document artifact kind")
    extension, allowed_content_type = _KIND_FORMATS[normalized_kind]
    normalized_content_type = str(content_type or "").strip().lower()
    if normalized_content_type != allowed_content_type:
        raise ValueError("Document artifact content type is not allowed for its kind")
    normalized_filename = _validate_filename(filename, extension=extension)
    return _ValidatedMetadata(
        tenant_id=normalized_tenant_id,
        document_id=normalized_document_id,
        kind=normalized_kind,
        filename=normalized_filename,
        content_type=normalized_content_type,
        extension=extension,
    )


def _positive_id(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _validate_filename(value: str, *, extension: str) -> str:
    filename = str(value or "").strip()
    if not filename or len(filename) > _MAX_FILENAME_LENGTH:
        raise ValueError("Document artifact filename is invalid")
    if PurePath(filename).name != filename or filename in {".", ".."}:
        raise ValueError("Document artifact filename must not contain a path")
    if filename.startswith(".") or not filename.lower().endswith(extension):
        raise ValueError(
            "Document artifact filename extension is not allowed for its kind"
        )
    for character in filename:
        category = unicodedata.category(character)
        if character in {'"', "'", ";", "\\"} or category.startswith("C"):
            raise ValueError("Document artifact filename contains unsafe characters")
    return filename


def _variant_for(*, tenant_id: int, document_id: int, kind: str) -> str:
    return f"tenant-{tenant_id}-document-{document_id}-{kind.replace('_', '-')}"


def _is_sha256(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )
