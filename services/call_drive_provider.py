"""Readonly personal Drive adapter, bounded to an explicitly selected folder."""

import re
from typing import Any

from services.analytics_google_providers import GoogleOAuthProvider
from services.document_drive_provider import DocumentDriveProviderFactory, GoogleDocumentDriveAdapter
from services.document_drive_contracts import DocumentDriveConnectionError

CALL_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
MAX_CALL_BYTES = 10 * 1024 * 1024
FILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,160}$")
CALL_FILE_FIELDS = "id,name,mimeType,size,md5Checksum,version,headRevisionId,modifiedTime,parents,trashed"


class CallDriveError(DocumentDriveConnectionError):
    pass


class GoogleCallDriveAdapter(GoogleDocumentDriveAdapter):
    async def metadata(self, file_id: str) -> dict:
        if not FILE_ID_PATTERN.fullmatch(file_id):
            raise CallDriveError("invalid_file_id", "Некорректный идентификатор файла")
        response = await self._request("GET", f"{self.BASE_URL}/files/{file_id}", params={"fields": CALL_FILE_FIELDS, "supportsAllDrives": "true"})
        if response.status_code != 200:
            raise self._provider_error(response)
        result = response.json()
        if not isinstance(result, dict):
            raise self._invalid_response()
        return result

    async def folder(self, folder_id: str) -> dict:
        result = await self.metadata(folder_id)
        if result.get("trashed") or result.get("mimeType") != "application/vnd.google-apps.folder":
            raise CallDriveError("call_folder_unavailable", "Выберите доступную папку Google Диска")
        return result

    async def list_recordings(self, folder_id: str, *, page_token: str | None = None) -> tuple[list[dict], str | None]:
        if not FILE_ID_PATTERN.fullmatch(folder_id):
            raise CallDriveError("invalid_folder_id", "Некорректная папка")
        response = await self._request("GET", f"{self.BASE_URL}/files", params={
            "q": f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
            "spaces": "drive", "pageSize": "5", "orderBy": "modifiedTime desc",
            "fields": f"files({CALL_FILE_FIELDS}),nextPageToken",
            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
            **({"pageToken": page_token} if page_token else {}),
        })
        if response.status_code != 200:
            raise self._provider_error(response)
        data = response.json()
        return list(data.get("files") or [])[:5], data.get("nextPageToken")

    async def download_audio(self, file_id: str) -> bytes:
        if not FILE_ID_PATTERN.fullmatch(file_id):
            raise CallDriveError("invalid_file_id", "Некорректный файл")
        async with self._client_factory() as client:
            async with client.stream("GET", f"{self.BASE_URL}/files/{file_id}", headers=self._headers, params={"alt": "media", "supportsAllDrives": "true"}) as response:
                if response.status_code != 200:
                    raise self._provider_error(response)
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_CALL_BYTES:
                        raise CallDriveError("call_audio_too_large", "Запись больше 10 МБ")
                    chunks.append(chunk)
                return b"".join(chunks)


class CallDriveProviderFactory(DocumentDriveProviderFactory):
    def authorization_url(self, *, redirect_uri: str, state: str) -> str:
        try:
            return GoogleOAuthProvider.build_authorization_url(client_secret_path=self._client_secret_path, redirect_uri=redirect_uri, state=state, scopes=(CALL_DRIVE_SCOPE,), include_granted_scopes=False)
        except Exception as exc:
            raise self._oauth_error(exc) from exc

    def exchange_code(self, *, redirect_uri: str, code: str) -> dict[str, Any]:
        try:
            credentials = GoogleOAuthProvider.exchange_authorization_code(client_secret_path=self._client_secret_path, redirect_uri=redirect_uri, code=code, scopes=(CALL_DRIVE_SCOPE,), allow_scope_superset=False).to_payload()
        except Exception as exc:
            raise self._oauth_error(exc) from exc
        credentials.pop("client_id", None)
        credentials.pop("client_secret", None)
        return credentials

    @staticmethod
    def _require_drive_file_scope(credentials: dict) -> None:
        raw = credentials.get("scopes") or []
        scopes = set(raw.split() if isinstance(raw, str) else raw)
        if scopes != {CALL_DRIVE_SCOPE}:
            raise CallDriveError("google_oauth_scope_mismatch", "Для записей требуется отдельное подключение только для чтения", status_code=409)

    def adapter(self, access_token_value: str, **kwargs) -> GoogleCallDriveAdapter:
        return GoogleCallDriveAdapter(access_token_value, client_factory=self._client_factory)


def get_call_drive_provider() -> CallDriveProviderFactory:
    return CallDriveProviderFactory()
