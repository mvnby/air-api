from io import BytesIO

import pytest
from docx import Document
from httpx import AsyncClient
from sqlmodel import select

from models import TenantAuditEvent
from services.document_drive_contracts import DocumentDriveConnectionError
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from tests.integration.test_managed_document_google_editing import FakeGoogleEditor
from tests.integration.test_manager_document_system_api import (
    BASE,
    _FakePdfConverter,
    _create_issuer,
    _create_native_contract_template,
    _legacy_owner_headers,
    _seed_order,
)


@pytest.fixture(autouse=True)
def _document_dependencies(monkeypatch, tmp_path):
    import importlib

    document_router = importlib.import_module("modules.documents.api.router")

    private = LocalPrivateAttachmentStorage(tmp_path / "document-google-api")
    provider = FakeGoogleEditor()

    async def get_provider(*, session, tenant_scope):
        assert session
        assert tenant_scope.tenant_id == 1
        return provider

    monkeypatch.setattr(
        document_router,
        "get_private_attachment_storage",
        lambda provider_name=None: private,
    )
    monkeypatch.setattr(document_router, "_pdf_converter", lambda: _FakePdfConverter())
    monkeypatch.setattr(
        document_router,
        "get_google_document_edit_provider",
        get_provider,
    )
    return provider


def _docx_text(content: bytes) -> str:
    document = Document(BytesIO(content))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


@pytest.mark.asyncio
async def test_managed_document_google_round_trip_api(
    async_client: AsyncClient,
    db,
    _document_dependencies: FakeGoogleEditor,
):
    headers = await _legacy_owner_headers(async_client)
    issuer_id = await _create_issuer(async_client, headers, name="ООО Онлайн API")
    template_id, _version_id = await _create_native_contract_template(
        async_client,
        headers,
        legal_entity_id=issuer_id,
    )
    order = await _seed_order(db)
    draft = await async_client.post(
        f"{BASE}/orders/{order.id}/documents/drafts",
        headers=headers,
        json={
            "legal_entity_id": issuer_id,
            "document_type": "contract",
            "issue_date": "2026-09-02",
            "issue_city": "Витебск",
            "template_id": template_id,
            "business_terms": {
                "contract_scenario": "services",
                "payment_schedule": [
                    {"share_percent": 100, "due_event": "before_work"}
                ],
            },
        },
    )
    assert draft.status_code == 200, draft.text
    document_id = int(draft.json()["id"])
    path = f"{BASE}/documents/{document_id}/google-edit-session"

    preview = await async_client.get(
        f"{BASE}/documents/{document_id}/preview",
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"].startswith("application/pdf")
    assert "inline" in preview.headers["content-disposition"]

    created = await async_client.post(path, headers=headers)
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "ready"
    assert created.json()["edit_url"].startswith("https://docs.google.com/")
    original_checksum = created.json()["base_checksum_sha256"]

    _document_dependencies.add_manual_paragraph("Ручная оговорка из браузера")
    changed = await async_client.get(path, headers=headers)
    assert changed.status_code == 200, changed.text
    assert changed.json()["status"] == "changed"

    synced = await async_client.post(
        f"{path}/sync",
        headers=headers,
        json={
            "expected_base_checksum_sha256": original_checksum,
            "expected_remote_revision": changed.json()["remote_revision"],
            "idempotency_key": "api-document-sync-1",
        },
    )
    assert synced.status_code == 200, synced.text
    assert synced.json()["status"] == "ready"
    assert synced.json()["base_checksum_sha256"] != original_checksum
    audit_event = (
        await db.execute(
            select(TenantAuditEvent).where(
                TenantAuditEvent.action == "order_document.google_sync",
                TenantAuditEvent.entity_id == document_id,
            )
        )
    ).scalar_one()
    assert audit_event.change_set["new_document_artifact_id"]

    issued = await async_client.post(
        f"{BASE}/documents/{document_id}/issue",
        headers=headers,
    )
    assert issued.status_code == 200, issued.text
    rendered = next(
        item for item in issued.json()["artifacts"] if item["kind"] == "rendered_docx"
    )
    downloaded = await async_client.get(
        f"{BASE}/artifacts/{rendered['id']}/download",
        headers=headers,
    )
    assert downloaded.status_code == 200
    text = _docx_text(downloaded.content)
    assert "Ручная оговорка из браузера" in text
    assert issued.json()["official_full_number"] in text


@pytest.mark.asyncio
async def test_managed_document_google_edit_rejects_unconnected_provider(
    async_client: AsyncClient,
    monkeypatch,
):
    import importlib

    document_router = importlib.import_module("modules.documents.api.router")

    async def disconnected(**_kwargs):
        raise DocumentDriveConnectionError(
            "google_drive_not_connected",
            "Google не подключён",
            status_code=409,
        )

    monkeypatch.setattr(
        document_router,
        "get_google_document_edit_provider",
        disconnected,
    )
    headers = await _legacy_owner_headers(async_client)
    response = await async_client.get(
        f"{BASE}/documents/999/google-edit-session",
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "google_drive_not_connected"
