"""Private storage boundary for immutable native DOCX template sources."""

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


DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_MAX_FILENAME_LENGTH = 255


@dataclass(frozen=True, slots=True)
class StoredTemplateSource:
    """Immutable source metadata suitable for ``DocumentTemplateVersion``."""

    tenant_id: int
    template_id: int
    version: int
    provider: str
    storage_key: str
    filename: str
    checksum_sha256: str
    size_bytes: int


class TemplateSourceStorage(Protocol):
    provider_name: str

    async def save(
        self,
        *,
        tenant_id: int,
        template_id: int,
        version: int,
        filename: str,
        content: bytes,
    ) -> StoredTemplateSource: ...

    async def read(self, source: StoredTemplateSource) -> bytes: ...

    async def read_persisted(
        self,
        *,
        tenant_id: int,
        template_id: int,
        version: int,
        storage_key: str,
        filename: str,
        checksum_sha256: str,
    ) -> bytes: ...


class PrivateTemplateSourceStorage:
    """Tenant/template/version-scoped adapter over private object storage.

    The immutable object key includes all ownership coordinates.  It is
    intentionally separate from rendered document artifacts so a future
    template editor cannot accidentally obtain document-artifact access.
    """

    def __init__(self, storage: PrivateAttachmentStorage) -> None:
        self._storage = VariantScopedPrivateAttachmentStorage(
            storage,
            variant_scope="document-templates",
        )
        self.provider_name = storage.provider_name

    async def save(
        self,
        *,
        tenant_id: int,
        template_id: int,
        version: int,
        filename: str,
        content: bytes,
    ) -> StoredTemplateSource:
        tenant_id = _positive_id(tenant_id, "tenant_id")
        template_id = _positive_id(template_id, "template_id")
        version = _positive_id(version, "version")
        filename = _validate_filename(filename)
        if not isinstance(content, bytes) or not content:
            raise ValueError("Template source must be non-empty bytes")

        checksum = sha256(content).hexdigest()
        stored = await self._storage.save(
            content=content,
            content_hash=checksum,
            extension="docx",
            content_type=DOCX_CONTENT_TYPE,
            variant=_variant_for(
                tenant_id=tenant_id,
                template_id=template_id,
                version=version,
            ),
        )
        return StoredTemplateSource(
            tenant_id=tenant_id,
            template_id=template_id,
            version=version,
            provider=stored.provider,
            storage_key=stored.storage_key,
            filename=filename,
            checksum_sha256=checksum,
            size_bytes=len(content),
        )

    async def read(self, source: StoredTemplateSource) -> bytes:
        source = _validate_source(source, expected_provider=self.provider_name)
        content = await self._storage.read(source.storage_key)
        if sha256(content).hexdigest() != source.checksum_sha256:
            raise ValueError("Template source SHA-256 verification failed")
        if len(content) != source.size_bytes:
            raise ValueError("Template source size verification failed")
        return content

    async def read_persisted(
        self,
        *,
        tenant_id: int,
        template_id: int,
        version: int,
        storage_key: str,
        filename: str,
        checksum_sha256: str,
    ) -> bytes:
        """Read a source reconstructed from a persisted template-version row.

        The current table intentionally stores the integrity digest but not a
        duplicate size column.  This still proves ownership and bytes against
        the persisted checksum; callers with :class:`StoredTemplateSource`
        additionally receive the size check in :meth:`read`.
        """
        _validate_persisted_identity(
            tenant_id=tenant_id,
            template_id=template_id,
            version=version,
            storage_key=storage_key,
            filename=filename,
            checksum_sha256=checksum_sha256,
        )
        content = await self._storage.read(storage_key)
        if sha256(content).hexdigest() != checksum_sha256:
            raise ValueError("Template source SHA-256 verification failed")
        return content


def _validate_source(
    source: StoredTemplateSource, *, expected_provider: str
) -> StoredTemplateSource:
    if not isinstance(source, StoredTemplateSource):
        raise TypeError("source must be StoredTemplateSource")
    if source.provider != expected_provider:
        raise ValueError("Template source belongs to another storage provider")
    _validate_persisted_identity(
        tenant_id=source.tenant_id,
        template_id=source.template_id,
        version=source.version,
        storage_key=source.storage_key,
        filename=source.filename,
        checksum_sha256=source.checksum_sha256,
    )
    if (
        not isinstance(source.size_bytes, int)
        or isinstance(source.size_bytes, bool)
        or source.size_bytes < 1
    ):
        raise ValueError("Template source size must be positive")
    return source


def _validate_persisted_identity(
    *,
    tenant_id: int,
    template_id: int,
    version: int,
    storage_key: str,
    filename: str,
    checksum_sha256: str,
) -> None:
    tenant_id = _positive_id(tenant_id, "tenant_id")
    template_id = _positive_id(template_id, "template_id")
    version = _positive_id(version, "version")
    _validate_filename(filename)
    if not _is_sha256(checksum_sha256):
        raise ValueError("Template source checksum must be a SHA-256 digest")
    expected_filename = f"document-templates-tenant-{tenant_id}-template-{template_id}-version-{version}.docx"
    if not str(storage_key or "").endswith(f"/{expected_filename}"):
        raise ValueError(
            "Template source storage key is outside its tenant/template scope"
        )


def _positive_id(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _validate_filename(value: str) -> str:
    filename = str(value or "").strip()
    if not filename or len(filename) > _MAX_FILENAME_LENGTH:
        raise ValueError("Template filename is invalid")
    if PurePath(filename).name != filename or filename in {".", ".."}:
        raise ValueError("Template filename must not contain a path")
    if filename.startswith(".") or not filename.lower().endswith(".docx"):
        raise ValueError("Template filename must use the .docx extension")
    for character in filename:
        if character in {'"', "'", ";", "\\"} or unicodedata.category(
            character
        ).startswith("C"):
            raise ValueError("Template filename contains unsafe characters")
    return filename


def _variant_for(*, tenant_id: int, template_id: int, version: int) -> str:
    return f"tenant-{tenant_id}-template-{template_id}-version-{version}"


def _is_sha256(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )
