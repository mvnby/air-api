from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import secrets
from typing import Any, Callable

import httpx

from services.analytics_google_providers import GoogleOAuthProvider, access_token
from services.analytics_provider_types import AnalyticsProviderError
from services.document_drive_contracts import (
    DocumentDriveAdapter,
    DocumentDriveConnectionError,
    DocumentDriveFolder,
)
from modules.documents.infrastructure.external_edit_provider import (
    DOCX_CONTENT_TYPE,
    DownloadedExternalEditFile,
    ExternalEditFileMetadata,
)


GOOGLE_DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
GOOGLE_DRIVE_FILE_SCOPES = (GOOGLE_DRIVE_FILE_SCOPE,)
MANAGED_FOLDER_NAME = "MVN CRM — Документы"
MAX_DOCUMENT_DRIVE_DOCX_BYTES = 5 * 1024 * 1024
_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
_ClientFactory = Callable[[], httpx.AsyncClient]


def _client_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20.0, trust_env=False)


class GoogleDocumentDriveAdapter:
    """Small Drive REST adapter bound to one tenant credential."""

    BASE_URL = "https://www.googleapis.com/drive/v3"
    UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
    provider_name = "google_drive"

    def __init__(
        self,
        access_token_value: str,
        *,
        connection_id: str = "pending",
        managed_folder_id: str | None = None,
        client_factory: _ClientFactory | None = None,
    ) -> None:
        self._access_token = access_token_value
        self.connection_id = connection_id
        self._managed_folder_id = managed_folder_id
        self._client_factory = client_factory or _client_factory

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    @staticmethod
    def _provider_error(response: httpx.Response) -> DocumentDriveConnectionError:
        if response.status_code in {401, 403}:
            return DocumentDriveConnectionError(
                "google_drive_access_denied",
                "Google Диск отклонил подключение или доступ был отозван",
            )
        return DocumentDriveConnectionError(
            "google_drive_unavailable",
            "Google Диск временно недоступен. Попробуйте ещё раз.",
            status_code=502,
        )

    async def account_label(self) -> str | None:
        response = await self._request(
            "GET",
            f"{self.BASE_URL}/about",
            params={"fields": "user(displayName,emailAddress)"},
        )
        if response.status_code != 200:
            raise self._provider_error(response)
        try:
            user = response.json().get("user") or {}
            return (
                str(user.get("emailAddress") or user.get("displayName") or "").strip()
                or None
            )
        except (TypeError, ValueError) as exc:
            raise DocumentDriveConnectionError(
                "google_drive_response_invalid",
                "Google Диск вернул некорректный ответ",
                status_code=502,
            ) from exc

    async def ensure_managed_folder(
        self,
        existing_folder_id: str | None,
    ) -> DocumentDriveFolder:
        if existing_folder_id:
            folder = await self._read_folder(existing_folder_id)
            if folder is not None:
                return folder
        response = await self._request(
            "POST",
            f"{self.BASE_URL}/files",
            headers={"Content-Type": "application/json"},
            params={"fields": "id,webViewLink"},
            json={
                "name": MANAGED_FOLDER_NAME,
                "mimeType": _FOLDER_MIME_TYPE,
                "appProperties": {"mvnPurpose": "document-root"},
            },
        )
        if response.status_code not in {200, 201}:
            raise self._provider_error(response)
        return self._folder_from_payload(response.json())

    async def _read_folder(self, folder_id: str) -> DocumentDriveFolder | None:
        response = await self._request(
            "GET",
            f"{self.BASE_URL}/files/{folder_id}",
            params={"fields": "id,mimeType,trashed,webViewLink"},
        )
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise self._provider_error(response)
        payload = response.json()
        if payload.get("trashed") or payload.get("mimeType") != _FOLDER_MIME_TYPE:
            return None
        return self._folder_from_payload(payload)

    @staticmethod
    def _folder_from_payload(payload: Any) -> DocumentDriveFolder:
        try:
            folder_id = str(payload["id"]).strip()
            url = str(payload.get("webViewLink") or "").strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise DocumentDriveConnectionError(
                "google_drive_response_invalid",
                "Google Диск вернул некорректный ответ",
                status_code=502,
            ) from exc
        if not folder_id:
            raise DocumentDriveConnectionError(
                "google_drive_response_invalid",
                "Google Диск не вернул идентификатор папки",
                status_code=502,
            )
        return DocumentDriveFolder(
            id=folder_id,
            web_view_url=url or f"https://drive.google.com/drive/folders/{folder_id}",
        )

    async def ensure_docx(
        self,
        *,
        edit_session_id: str,
        filename: str,
        content: bytes,
    ) -> ExternalEditFileMetadata:
        folder_id = self._required_runtime_folder()
        escaped_session_id = edit_session_id.replace("'", "\\'")
        query = (
            "trashed = false and "
            f"'{folder_id}' in parents and "
            "appProperties has { key='mvnEditSessionId' and "
            f"value='{escaped_session_id}' }}"
        )
        response = await self._request(
            "GET",
            f"{self.BASE_URL}/files",
            params={
                "q": query,
                "spaces": "drive",
                "pageSize": "2",
                "fields": f"files({self._metadata_fields()})",
            },
        )
        if response.status_code != 200:
            raise self._provider_error(response)
        try:
            matches = list(response.json().get("files") or [])
        except (TypeError, ValueError) as exc:
            raise self._invalid_response() from exc
        if matches:
            return self._external_metadata(matches[0])

        metadata = {
            "name": filename,
            "mimeType": DOCX_CONTENT_TYPE,
            "parents": [folder_id],
            "appProperties": {"mvnEditSessionId": edit_session_id},
        }
        boundary = f"mvn-{secrets.token_hex(16)}"
        while boundary.encode() in content:
            boundary = f"mvn-{secrets.token_hex(16)}"
        body = (
            (
                f"--{boundary}\r\n"
                "Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(metadata, ensure_ascii=False)}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: {DOCX_CONTENT_TYPE}\r\n\r\n"
            ).encode("utf-8")
            + content
            + f"\r\n--{boundary}--\r\n".encode("ascii")
        )
        response = await self._request(
            "POST",
            self.UPLOAD_URL,
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            params={"uploadType": "multipart", "fields": self._metadata_fields()},
            content=body,
        )
        if response.status_code not in {200, 201}:
            raise self._provider_error(response)
        return self._external_metadata(response.json())

    async def get_metadata(self, file_id: str) -> ExternalEditFileMetadata:
        response = await self._request(
            "GET",
            f"{self.BASE_URL}/files/{file_id}",
            params={"fields": self._metadata_fields()},
        )
        if response.status_code != 200:
            raise self._provider_error(response)
        return self._external_metadata(response.json())

    async def download_docx(self, file_id: str) -> DownloadedExternalEditFile:
        metadata = await self.get_metadata(file_id)
        if metadata.mime_type != DOCX_CONTENT_TYPE:
            raise DocumentDriveConnectionError(
                "google_drive_file_type_changed",
                "Файл в Google Диске больше не является DOCX",
            )
        content = await self._download_bounded(
            f"{self.BASE_URL}/files/{file_id}",
            params={"alt": "media"},
        )
        return DownloadedExternalEditFile(metadata=metadata, content=content)

    async def _download_bounded(self, url: str, **kwargs: Any) -> bytes:
        try:
            async with self._client_factory() as client:
                async with client.stream(
                    "GET",
                    url,
                    headers=self._headers,
                    **kwargs,
                ) as response:
                    if response.status_code != 200:
                        raise self._provider_error(response)
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > MAX_DOCUMENT_DRIVE_DOCX_BYTES:
                        raise self._oversized_file()
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_DOCUMENT_DRIVE_DOCX_BYTES:
                            raise self._oversized_file()
                        chunks.append(chunk)
                    return b"".join(chunks)
        except DocumentDriveConnectionError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise DocumentDriveConnectionError(
                "google_drive_unavailable",
                "Google Диск временно недоступен. Попробуйте ещё раз.",
                status_code=502,
            ) from exc

    @staticmethod
    def _oversized_file() -> DocumentDriveConnectionError:
        return DocumentDriveConnectionError(
            "google_drive_file_too_large",
            "DOCX в Google Диске превышает 5 МБ",
        )

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            async with self._client_factory() as client:
                return await client.request(
                    method,
                    url,
                    headers={**self._headers, **(headers or {})},
                    **kwargs,
                )
        except httpx.HTTPError as exc:
            raise DocumentDriveConnectionError(
                "google_drive_unavailable",
                "Google Диск временно недоступен. Попробуйте ещё раз.",
                status_code=502,
            ) from exc

    def _required_runtime_folder(self) -> str:
        if not self._managed_folder_id:
            raise DocumentDriveConnectionError(
                "google_drive_folder_unavailable",
                "Рабочая папка Google Диска не настроена",
                status_code=409,
            )
        return self._managed_folder_id

    @staticmethod
    def _metadata_fields() -> str:
        return (
            "id,webViewLink,name,mimeType,modifiedTime,headRevisionId,"
            "md5Checksum,parents,appProperties"
        )

    def _external_metadata(self, payload: Any) -> ExternalEditFileMetadata:
        try:
            file_id = str(payload["id"]).strip()
            edit_url = str(payload.get("webViewLink") or "").strip()
            filename = str(payload["name"]).strip()
            mime_type = str(payload["mimeType"]).strip()
            revision = str(
                payload.get("headRevisionId") or payload.get("md5Checksum") or ""
            ).strip()
            modified_raw = str(payload.get("modifiedTime") or "").strip()
            parents = {str(value) for value in (payload.get("parents") or [])}
            app_properties = payload.get("appProperties") or {}
            if not isinstance(app_properties, dict):
                raise TypeError("appProperties must be an object")
            edit_session_id = str(app_properties.get("mvnEditSessionId") or "").strip()
            modified_at = (
                datetime.fromisoformat(modified_raw.replace("Z", "+00:00"))
                if modified_raw
                else None
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise self._invalid_response() from exc
        if not all((file_id, edit_url, filename, mime_type, revision)):
            raise self._invalid_response()
        if self._managed_folder_id and self._managed_folder_id not in parents:
            raise DocumentDriveConnectionError(
                "google_drive_file_outside_managed_folder",
                "Файл находится вне рабочей папки CRM",
            )
        if not edit_session_id:
            raise DocumentDriveConnectionError(
                "google_drive_file_not_managed",
                "Файл не принадлежит сессии редактирования CRM",
            )
        return ExternalEditFileMetadata(
            file_id=file_id,
            edit_session_id=edit_session_id,
            edit_url=edit_url,
            filename=filename,
            mime_type=mime_type,
            revision=revision,
            modified_at=modified_at,
        )

    @staticmethod
    def _invalid_response() -> DocumentDriveConnectionError:
        return DocumentDriveConnectionError(
            "google_drive_response_invalid",
            "Google Диск вернул некорректный ответ",
            status_code=502,
        )


class DocumentDriveProviderFactory:
    """OAuth and adapter factory independent from persistence and token.json."""

    def __init__(
        self,
        *,
        client_secret_path: str | Path = "client_secret.json",
        client_factory: _ClientFactory | None = None,
    ) -> None:
        self._client_secret_path = client_secret_path
        self._client_factory = client_factory

    def authorization_url(self, *, redirect_uri: str, state: str) -> str:
        try:
            return GoogleOAuthProvider.build_authorization_url(
                client_secret_path=self._client_secret_path,
                redirect_uri=redirect_uri,
                state=state,
                scopes=GOOGLE_DRIVE_FILE_SCOPES,
                include_granted_scopes=False,
            )
        except Exception as exc:
            raise self._oauth_error(exc) from exc

    def exchange_code(self, *, redirect_uri: str, code: str) -> dict[str, Any]:
        try:
            credentials = GoogleOAuthProvider.exchange_authorization_code(
                client_secret_path=self._client_secret_path,
                redirect_uri=redirect_uri,
                code=code,
                scopes=GOOGLE_DRIVE_FILE_SCOPES,
                allow_scope_superset=False,
            ).to_payload()
        except Exception as exc:
            raise self._oauth_error(exc) from exc
        credentials.pop("client_id", None)
        credentials.pop("client_secret", None)
        return credentials

    async def access_token(self, credentials: dict[str, Any]) -> str:
        self._require_drive_file_scope(credentials)
        try:
            token = await access_token(
                credentials,
                client_factory=self._client_factory,
                client_secret_path=self._client_secret_path,
            )
        except Exception as exc:
            raise self._oauth_error(exc) from exc
        self._require_drive_file_scope(credentials)
        return token

    def adapter(
        self,
        access_token_value: str,
        *,
        connection_id: str = "pending",
        managed_folder_id: str | None = None,
    ) -> DocumentDriveAdapter:
        return GoogleDocumentDriveAdapter(
            access_token_value,
            connection_id=connection_id,
            managed_folder_id=managed_folder_id,
            client_factory=self._client_factory,
        )

    @staticmethod
    def _oauth_error(exc: Exception) -> DocumentDriveConnectionError:
        if isinstance(exc, DocumentDriveConnectionError):
            return exc
        if isinstance(exc, AnalyticsProviderError) and exc.code.endswith(
            "access_denied"
        ):
            return DocumentDriveConnectionError(
                "google_drive_access_denied",
                "Google отклонил подключение или доступ был отозван",
            )
        return DocumentDriveConnectionError(
            "google_oauth_unavailable",
            "Не удалось подключить Google Диск. Попробуйте ещё раз.",
            status_code=502,
        )

    @staticmethod
    def _require_drive_file_scope(credentials: dict[str, Any]) -> None:
        raw_scopes = credentials.get("scopes") or ()
        scopes = (
            {item for item in str(raw_scopes).split() if item}
            if isinstance(raw_scopes, str)
            else {str(item) for item in raw_scopes}
        )
        if scopes != {GOOGLE_DRIVE_FILE_SCOPE}:
            raise DocumentDriveConnectionError(
                "google_oauth_scope_mismatch",
                "Подключение Google Диска запросило лишние права",
                status_code=409,
            )


def get_document_drive_provider() -> DocumentDriveProviderFactory:
    return DocumentDriveProviderFactory()
