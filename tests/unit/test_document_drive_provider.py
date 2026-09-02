from datetime import datetime, timezone

import httpx
import pytest

from modules.documents.infrastructure.external_edit_provider import DOCX_CONTENT_TYPE
from services.document_drive_provider import (
    GOOGLE_DRIVE_FILE_SCOPES,
    MAX_DOCUMENT_DRIVE_DOCX_BYTES,
    DocumentDriveProviderFactory,
    GoogleDocumentDriveAdapter,
)
from services.document_drive_contracts import DocumentDriveConnectionError


def _factory(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_authorization_uses_only_drive_file_scope(monkeypatch):
    captured = {}

    def build_authorization_url(**kwargs):
        captured.update(kwargs)
        return "https://accounts.google.com/auth"

    monkeypatch.setattr(
        "services.document_drive_provider.GoogleOAuthProvider.build_authorization_url",
        build_authorization_url,
    )
    provider = DocumentDriveProviderFactory(client_secret_path="platform-client.json")

    assert provider.authorization_url(
        redirect_uri="https://api.mvn.by/api/manager/google-auth/callback",
        state="safe-state",
    ) == "https://accounts.google.com/auth"
    assert captured["scopes"] == GOOGLE_DRIVE_FILE_SCOPES
    assert captured["include_granted_scopes"] is False


def test_exchange_rejects_scope_superset(monkeypatch):
    def exchange_authorization_code(**kwargs):
        assert kwargs["allow_scope_superset"] is False
        raise RuntimeError("unexpected scope union")

    monkeypatch.setattr(
        "services.document_drive_provider.GoogleOAuthProvider.exchange_authorization_code",
        exchange_authorization_code,
    )
    provider = DocumentDriveProviderFactory(client_secret_path="platform-client.json")

    with pytest.raises(DocumentDriveConnectionError, match="Не удалось подключить Google Диск"):
        provider.exchange_code(redirect_uri="https://api.mvn.by/callback", code="code")


@pytest.mark.asyncio
async def test_adapter_uploads_docx_to_tenant_managed_folder_idempotently():
    calls = []
    payload = {
        "id": "docx-file",
        "webViewLink": "https://drive.google.com/file/d/docx-file/view",
        "name": "Договор.docx",
        "mimeType": DOCX_CONTENT_TYPE,
        "modifiedTime": "2026-09-02T09:15:00Z",
        "headRevisionId": "revision-1",
        "md5Checksum": "checksum-1",
        "parents": ["folder-21"],
        "appProperties": {"mvnEditSessionId": "session-123"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"files": []})
        assert request.url.path == "/upload/drive/v3/files"
        assert request.url.params["uploadType"] == "multipart"
        assert "multipart/related" in request.headers["content-type"]
        assert b"mvnEditSessionId" in request.content
        assert b"docx-bytes" in request.content
        return httpx.Response(200, json=payload)

    adapter = GoogleDocumentDriveAdapter(
        "access-token",
        connection_id="7:key",
        managed_folder_id="folder-21",
        client_factory=_factory(handler),
    )

    metadata = await adapter.ensure_docx(
        edit_session_id="session-123",
        filename="Договор.docx",
        content=b"docx-bytes",
    )

    assert metadata.file_id == "docx-file"
    assert metadata.revision == "revision-1"
    assert metadata.modified_at == datetime(2026, 9, 2, 9, 15, tzinfo=timezone.utc)
    assert adapter.provider_name == "google_drive"
    assert adapter.connection_id == "7:key"
    assert len(calls) == 2
    assert "folder-21" in calls[0].url.params["q"]


@pytest.mark.asyncio
async def test_adapter_download_preserves_docx_metadata():
    payload = {
        "id": "docx-file",
        "webViewLink": "https://drive.google.com/file/d/docx-file/view",
        "name": "Договор.docx",
        "mimeType": DOCX_CONTENT_TYPE,
        "modifiedTime": "2026-09-02T09:15:00Z",
        "headRevisionId": "revision-2",
        "parents": ["folder-21"],
        "appProperties": {"mvnEditSessionId": "session-123"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, content=b"edited-docx")
        return httpx.Response(200, json=payload)

    adapter = GoogleDocumentDriveAdapter(
        "access-token",
        connection_id="7:key",
        managed_folder_id="folder-21",
        client_factory=_factory(handler),
    )

    downloaded = await adapter.download_docx("docx-file")

    assert downloaded.content == b"edited-docx"
    assert downloaded.metadata.file_id == "docx-file"
    assert downloaded.metadata.revision == "revision-2"


@pytest.mark.asyncio
async def test_adapter_rejects_oversized_docx_before_buffering_body():
    payload = {
        "id": "docx-file",
        "webViewLink": "https://drive.google.com/file/d/docx-file/view",
        "name": "Договор.docx",
        "mimeType": DOCX_CONTENT_TYPE,
        "modifiedTime": "2026-09-02T09:15:00Z",
        "headRevisionId": "revision-2",
        "parents": ["folder-21"],
        "appProperties": {"mvnEditSessionId": "session-123"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("alt") == "media":
            return httpx.Response(
                200,
                headers={"Content-Length": str(MAX_DOCUMENT_DRIVE_DOCX_BYTES + 1)},
                content=b"",
            )
        return httpx.Response(200, json=payload)

    adapter = GoogleDocumentDriveAdapter(
        "access-token",
        connection_id="7:key",
        managed_folder_id="folder-21",
        client_factory=_factory(handler),
    )

    with pytest.raises(DocumentDriveConnectionError, match="5 МБ"):
        await adapter.download_docx("docx-file")


@pytest.mark.asyncio
async def test_runtime_rejects_credentials_with_extra_google_scopes():
    provider = DocumentDriveProviderFactory(client_secret_path="platform-client.json")

    with pytest.raises(DocumentDriveConnectionError) as exc_info:
        await provider.access_token(
            {
                "access_token": "token",
                "refresh_token": "refresh",
                "scopes": [
                    GOOGLE_DRIVE_FILE_SCOPES[0],
                    "https://www.googleapis.com/auth/analytics.readonly",
                ],
            }
        )

    assert exc_info.value.code == "google_oauth_scope_mismatch"
