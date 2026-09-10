from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from core.config import settings
from core.integration_credential_keyring import (
    DecryptedIntegrationCredential,
    IntegrationCredentialUnavailable,
    IntegrationCredentialUnreadable,
    InvalidIntegrationCredentialKeyring,
)
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
    """Tenant-bound Drive credentials with transitional legacy reads."""

    _ENCRYPTION_CONTEXT = b"mvn.document-drive.credentials.fernet.v1"
    _FINGERPRINT_CONTEXT = b"mvn.document-drive.credentials.fingerprint.v1"

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
        raw = json.dumps(
            envelope,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        keyring = settings.integration_credential_keyring
        try:
            if keyring.enabled and keyring.write_mode == "active":
                return keyring.encrypt(raw, context=cls._ENCRYPTION_CONTEXT)
            return keyring.encrypt_legacy(
                raw,
                context=cls._ENCRYPTION_CONTEXT,
                local_legacy_secret=str(settings.SECRET_KEY or ""),
            )
        except (IntegrationCredentialUnavailable, InvalidIntegrationCredentialKeyring) as exc:
            raise cls._unavailable() from exc

    @classmethod
    def decrypt(
        cls,
        encrypted: str,
        *,
        tenant_id: int,
        provider: str,
    ) -> dict[str, Any]:
        payload, _ = cls.decrypt_with_source(
            encrypted,
            tenant_id=tenant_id,
            provider=provider,
        )
        return payload

    @classmethod
    def decrypt_with_source(
        cls,
        encrypted: str,
        *,
        tenant_id: int,
        provider: str,
    ) -> tuple[dict[str, Any], DecryptedIntegrationCredential]:
        try:
            decrypted = settings.integration_credential_keyring.decrypt(
                encrypted,
                context=cls._ENCRYPTION_CONTEXT,
                local_legacy_secret=str(settings.SECRET_KEY or ""),
            )
            envelope = json.loads(decrypted.plaintext)
        except IntegrationCredentialUnavailable as exc:
            raise cls._unavailable() from exc
        except (
            IntegrationCredentialUnreadable,
            InvalidIntegrationCredentialKeyring,
            UnicodeError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise cls._unreadable() from exc
        if (
            not isinstance(envelope, dict)
            or envelope.get("version") != 1
            or envelope.get("tenant_id") != int(tenant_id)
            or envelope.get("provider") != str(provider)
        ):
            raise cls._unreadable()
        payload = envelope.get("credentials")
        if not isinstance(payload, dict) or not all(
            isinstance(key, str) for key in payload
        ):
            raise cls._unreadable()
        return payload, decrypted

    @classmethod
    def fingerprint(cls, payload: dict[str, Any]) -> str:
        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        keyring = settings.integration_credential_keyring
        try:
            if keyring.enabled and keyring.write_mode == "active":
                return keyring.fingerprint(
                    serialized.encode("utf-8"),
                    context=cls._FINGERPRINT_CONTEXT,
                )
            return keyring.fingerprint_legacy(
                serialized.encode("utf-8"),
                context=cls._FINGERPRINT_CONTEXT,
                local_legacy_secret=str(settings.SECRET_KEY or ""),
            )
        except (IntegrationCredentialUnavailable, InvalidIntegrationCredentialKeyring) as exc:
            raise cls._unavailable() from exc

    @staticmethod
    def _unavailable() -> DocumentDriveConnectionError:
        return DocumentDriveConnectionError(
            "credential_encryption_unavailable",
            "Хранилище подключений временно недоступно",
            status_code=503,
        )

    @staticmethod
    def _unreadable() -> DocumentDriveConnectionError:
        return DocumentDriveConnectionError(
            "credentials_unreadable",
            "Подключение Google Диска сохранено, но временно недоступно",
            status_code=503,
        )


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
