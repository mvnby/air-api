"""Provider boundary for browser-based editing of DOCX files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@dataclass(frozen=True, slots=True)
class ExternalEditFileMetadata:
    file_id: str
    edit_session_id: str
    edit_url: str
    filename: str
    mime_type: str
    revision: str
    modified_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DownloadedExternalEditFile:
    metadata: ExternalEditFileMetadata
    content: bytes


class ExternalEditProvider(Protocol):
    """A tenant-bound editor; implementations must never use global auth."""

    provider_name: str
    connection_id: str

    async def ensure_docx(
        self,
        *,
        edit_session_id: str,
        filename: str,
        content: bytes,
    ) -> ExternalEditFileMetadata:
        """Idempotently create/find one file for ``edit_session_id``."""

    async def get_metadata(self, file_id: str) -> ExternalEditFileMetadata: ...

    async def download_docx(self, file_id: str) -> DownloadedExternalEditFile: ...
