import importlib
import shutil
from copy import deepcopy
from email.parser import BytesParser
from email.policy import default
from io import BytesIO

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from PIL import Image

from models import Customer, DocumentExternalEditSession
from modules.documents.application.managed_document_external_edits import (
    ManagedDocumentExternalEditSessionService,
)
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from tests.integration.test_managed_document_google_editing import FakeGoogleEditor
from tests.integration.test_managed_document_lifecycle import (
    FakePdfConverter,
    _draft,
    _seed,
    _template_docx,
)
from tests.integration.test_manager_document_system_api import (
    BASE,
    DOCX_MIME,
    _create_issuer,
    _create_native_template,
    _legacy_owner_headers,
    _local_document_storage,  # noqa: F401 -- autouse storage fixture
    _seed_order,
)


@pytest.mark.asyncio
async def test_draft_parameter_api_updates_existing_draft_and_rejects_stale_or_wrong_terms(
    async_client, db
):
    headers = await _legacy_owner_headers(async_client)
    issuer_id = await _create_issuer(async_client, headers, name="ООО Параметры")
    template_id, _ = await _create_native_template(
        async_client, headers, legal_entity_id=issuer_id
    )
    order = await _seed_order(db)
    created = await async_client.post(
        f"{BASE}/orders/{order.id}/documents/drafts",
        headers=headers,
        json={
            "legal_entity_id": issuer_id,
            "document_type": "contract",
            "issue_date": "2026-10-09",
            "template_id": template_id,
            "business_terms": {
                "contract_scenario": "services",
                "payment_schedule": [
                    {"share_percent": 100, "due_event": "before_work"}
                ],
            },
        },
    )
    assert created.status_code == 200, created.text
    document_id = created.json()["id"]
    url = f"{BASE}/documents/{document_id}/draft/parameters"
    parameters = await async_client.get(url, headers=headers)
    assert parameters.status_code == 200, parameters.text
    body = parameters.json()
    assert body["issue_date"] == "2026-10-09"
    assert body["business_terms"]["contract_scenario"] == "services"
    assert not body["has_editable_copy"]
    changed = await async_client.patch(
        url,
        headers=headers,
        json={"expected_revision": body["revision"], "issue_date": "2026-10-01"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["id"] == document_id
    assert changed.json()["date"].startswith("2026-10-01")
    assert changed.json()["official_number"] is None
    stale = await async_client.patch(
        url,
        headers=headers,
        json={"expected_revision": body["revision"], "issue_date": "2026-10-02"},
    )
    assert stale.status_code == 409, stale.text
    current = (await async_client.get(url, headers=headers)).json()
    incompatible = await async_client.patch(
        url,
        headers=headers,
        json={
            "expected_revision": current["revision"],
            "consumer_terms": {"equipment_model": "Не B2C"},
        },
    )
    assert incompatible.status_code == 400, incompatible.text
    null_date = await async_client.patch(
        url,
        headers=headers,
        json={"expected_revision": current["revision"], "issue_date": None},
    )
    assert null_date.status_code == 422
    listed = (
        await async_client.get(f"{BASE}/orders/{order.id}/documents", headers=headers)
    ).json()
    assert len(listed["items"]) == 1
    assert listed["items"][0]["date"].startswith("2026-10-01")


@pytest.mark.asyncio
async def test_apply_template_version_preserves_frozen_draft_and_protects_manual_copy(
    async_client,
    db,
    tmp_path,
    monkeypatch,
):
    headers = await _legacy_owner_headers(async_client)
    scope, order, issuer, templates, artifacts = await _seed(db, tmp_path)
    draft = await _draft(db, scope=scope, order=order, issuer=issuer)
    # API upload/readiness must use the same private storage as the service fixture.
    document_router = importlib.import_module("modules.documents.api.router")
    monkeypatch.setattr(
        document_router,
        "get_private_attachment_storage",
        lambda provider=None: LocalPrivateAttachmentStorage(tmp_path / "private-documents"),
    )
    original_version = draft.template_version_id
    frozen = deepcopy(draft.render_snapshot)
    draft_url = f"{BASE}/documents/{draft.id}/draft/parameters"
    versions_url = f"{BASE}/templates/{draft.document_template_id}/versions"
    scoped = {"legal_entity_id": issuer.id}
    source = Document(BytesIO(_template_docx()))
    source.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    source.add_paragraph("УНП {{ customer.unp }}")
    content = BytesIO()
    source.save(content)
    uploaded = await async_client.post(
        versions_url,
        headers=headers,
        data=scoped,
        files={"file": ("исправлен.docx", content.getvalue(), DOCX_MIME)},
    )
    assert uploaded.status_code == 200, uploaded.text
    next_id = uploaded.json()["id"]
    params = (await async_client.get(draft_url, headers=headers)).json()
    assert params["template_version_id"] == original_version
    change = {"expected_revision": params["revision"], "template_version_id": next_id}
    assert (
        await async_client.patch(draft_url, headers=headers, json=change)
    ).status_code == 409
    activate = f"{versions_url}/{next_id}/activate"
    assert (
        await async_client.post(
            activate,
            headers=headers,
            params={
                **scoped,
                "expected_active_version_id": next_id,
            },
        )
    ).status_code == 409
    activated = await async_client.post(
        activate,
        headers=headers,
        params={
            **scoped,
            "expected_active_version_id": original_version,
        },
    )
    assert activated.status_code == 200, activated.text

    customer = await db.get(Customer, order.customer_id)
    customer.full_legal_name = "Новые реквизиты вне снимка"
    await db.commit()
    editor = await ManagedDocumentExternalEditSessionService.ensure_session(
        db,
        tenant_scope=scope,
        document_id=draft.id,
        template_storage=templates,
        artifact_storage=artifacts,
        provider=FakeGoogleEditor(),
    )
    editor_id = editor.id
    stale = await async_client.patch(draft_url, headers=headers, json=change)
    assert stale.status_code == 409
    params = (await async_client.get(draft_url, headers=headers)).json()
    change["expected_revision"] = params["revision"]
    assert params["has_editable_copy"]
    assert (
        await async_client.patch(draft_url, headers=headers, json=change)
    ).status_code == 409
    assert await db.get(DocumentExternalEditSession, editor_id)
    _, other_version = await _create_native_template(
        async_client, headers, legal_entity_id=issuer.id
    )
    assert (
        await async_client.patch(
            draft_url,
            headers=headers,
            json={
                **change,
                "reset_editable_copy": True,
                "template_version_id": other_version,
            },
        )
    ).status_code == 409
    response = await async_client.patch(
        draft_url,
        headers=headers,
        json={**change, "reset_editable_copy": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["template_version_id"] == next_id
    assert response.json()["customer_readiness"]["can_issue"]
    assert response.json()["customer_readiness"]["missing_fields"]
    await db.refresh(draft)
    assert draft.official_number is None and draft.status == "draft"
    assert draft.render_snapshot["values"] == frozen["values"]
    assert draft.render_snapshot["table_rows"] == frozen["table_rows"]
    assert not (await async_client.get(draft_url, headers=headers)).json()[
        "has_editable_copy"
    ]

    produced = []

    class InspectPreview(FakePdfConverter):
        def convert_docx(self, content, *, filename):
            rendered = Document(BytesIO(content))
            heading = next(
                p for p in rendered.paragraphs if p.text.startswith("Договор №")
            )
            assert heading.alignment == WD_ALIGN_PARAGRAPH.RIGHT
            result = BytesIO()
            Image.new("RGB", (64, 80), (30, 80, 170)).save(result, "PDF")
            produced.append(result.getvalue())
            return produced[-1]

    monkeypatch.setattr(document_router, "_pdf_converter", InspectPreview)
    preview = await async_client.get(
        f"{BASE}/documents/{draft.id}/preview?include_first_page=true", headers=headers
    )
    assert preview.status_code == 200, (
        preview.text[:180] if preview.status_code != 200 else ""
    )
    assert len(produced) == 1
    assert preview.headers["cache-control"] == "private, no-store"
    if shutil.which("pdftoppm"):
        message = BytesParser(policy=default).parsebytes(
            f"Content-Type: {preview.headers['content-type']}\r\n\r\n".encode()
            + preview.content
        )
        parts = {
            part.get_param("name", header="content-disposition"): part
            for part in message.iter_parts()
        }
        assert parts["pdf"].get_payload(decode=True) == produced[0]
        page = Image.open(BytesIO(parts["first_page"].get_payload(decode=True)))
        assert page.format == "PNG"
        red, green, blue = page.getpixel((page.width // 2, page.height // 2))
        assert blue > green > red
    else:
        assert preview.headers["content-type"] == "application/pdf"
        assert preview.content == produced[0]
