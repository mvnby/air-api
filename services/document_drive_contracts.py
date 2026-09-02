from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Protocol

from cryptography.fernet import Fernet, InvalidToken

from core.config import settings
from modules.documents.infrastructure.external_edit_provider import (
    DownloadedExternalEditFile,
    ExternalEditFileMetadata,
)


class DocumentDriveConnectionError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class DocumentDriveCredentialCipher:
    """Authenticated encryption isolated from other integration domains."""

    _ENCRYPTION_CONTEXT = b"mvn.document-drive.credentials.fernet.v1"
    _FINGERPRINT_CONTEXT = b"mvn.document-drive.credentials.fingerprint.v1"

    @classmethod
    def _fernet(cls) -> Fernet:
        secret = str(settings.SECRET_KEY or "").encode("utf-8")
        if len(secret) < 16:
            raise DocumentDriveConnectionError(
                "credential_encryption_unavailable",
                "Хранилище подключений временно недоступно",
                status_code=503,
            )
        key = hmac.new(secret, cls._ENCRYPTION_CONTEXT, hashlib.sha256).digest()
        return Fernet(base64.urlsafe_b64encode(key))

    @classmethod
    def encrypt(
        cls,
        payload: dict[str, Any],
        *,
        tenant_id: int,
        provider: str,
    ) -> str:
        envelope = {
            "version": 1,
            "tenant_id": int(tenant_id),
            "provider": str(provider),
            "credentials": payload,
        }
        raw = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode()
        return cls._fernet().encrypt(raw).decode("ascii")

    @classmethod
    def decrypt(
        cls,
        encrypted: str,
        *,
        tenant_id: int,
        provider: str,
    ) -> dict[str, Any]:
        try:
            raw = cls._fernet().decrypt(encrypted.encode("ascii"))
            envelope = json.loads(raw)
        except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise DocumentDriveConnectionError(
                "credentials_unreadable",
                "Подключение Google Диска нужно настроить заново",
                status_code=503,
            ) from exc
        if (
            not isinstance(envelope, dict)
            or envelope.get("version") != 1
            or envelope.get("tenant_id") != int(tenant_id)
            or envelope.get("provider") != str(provider)
        ):
            raise DocumentDriveConnectionError(
                "credentials_unreadable",
                "Подключение Google Диска нужно настроить заново",
                status_code=503,
            )
        payload = envelope.get("credentials")
        if not isinstance(payload, dict) or not all(
            isinstance(key, str) for key in payload
        ):
            raise DocumentDriveConnectionError(
                "credentials_unreadable",
                "Подключение Google Диска нужно настроить заново",
                status_code=503,
            )
        return payload

    @classmethod
    def fingerprint(cls, payload: dict[str, Any]) -> str:
        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        key = str(settings.SECRET_KEY or "").encode("utf-8")
        return hmac.new(
            key,
            cls._FINGERPRINT_CONTEXT + serialized.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


@dataclass(frozen=True)
class DocumentDriveFolder:
    id: str
    web_view_url: str


class DocumentDriveAdapter(Protocol):
    provider_name: str
    connection_id: str

    async def account_label(self) -> str | None: ...

    async def ensure_managed_folder(
        self,
        existing_folder_id: str | None,
    ) -> DocumentDriveFolder: ...

    async def ensure_docx(
        self,
        *,
        edit_session_id: str,
        filename: str,
        content: bytes,
    ) -> ExternalEditFileMetadata: ...

    async def get_metadata(self, file_id: str) -> ExternalEditFileMetadata: ...

    async def download_docx(self, file_id: str) -> DownloadedExternalEditFile: ...


@dataclass(frozen=True)
class DocumentDriveRuntime:
    adapter: DocumentDriveAdapter
    managed_folder_id: str
