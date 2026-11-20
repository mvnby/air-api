"""Scoped MCP tool dispatch, official file delivery and retry behavior."""

from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from modules.documents.application.external_order_documents import (
    ExternalDocumentVersionConflictError,
    ExternalDocumentWriteResult,
    ExternalOrderDocumentService,
)
from schemas_order_diagnostics import OrderTechnicalActPrepared
from services.connector_file_service import ConnectorFileService, ConnectorFileUnavailable
from services.connector_order_documents import OrderTechnicalActService
from services.connector_mcp_tools import ORDER_DOCS_UPLOAD_SCOPE, TOOLS
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from tests.unit.test_connector_mcp_transport import _rpc, mcp_client


@pytest.mark.parametrize("name", [
    "register_external_order_contract", "upload_order_document", "attach_order_document_file",
])
def test_external_upload_discovery_uses_official_input_and_opt_in_scope(name):
    tool = TOOLS[name].definition()
    assert tool.meta["openai/fileParams"] == ["file"]
    assert tool.meta["securitySchemes"][0]["scopes"] == ["kitlane:read", ORDER_DOCS_UPLOAD_SCOPE]
    assert not tool.annotations.readOnlyHint and tool.annotations.idempotentHint
    file_schema = tool.inputSchema["$defs"]["OpenAIFile"]
    assert set(file_schema["required"]) == {"file_id", "download_url"}
    assert set(file_schema["properties"]) == {"file_id", "download_url", "file_name", "mime_type"}


def test_order_document_and_inspection_reads_are_scoped_and_bounded():
    read = TOOLS["list_order_documents"].definition()
    assert read.annotations.readOnlyHint
    assert read.inputSchema["properties"]["limit"]["maximum"] == 100
    assert {"site_id", "equipment_id", "document_type"} <= read.inputSchema["properties"].keys()
    inspection = TOOLS["get_order_inspection"].definition()
    assert inspection.annotations.readOnlyHint
    assert set(inspection.inputSchema["required"]) == {"order_id", "site_id", "equipment_id"}


@pytest.mark.asyncio
async def test_document_upload_rejects_plain_read_and_foreign_order_before_manager_link(mcp_client, monkeypatch):
    client, access, _, _ = mcp_client
    checked = []

    async def get_order(session, scope, order_id):
        checked.append((scope.tenant_id, order_id))
        raise LookupError("unavailable order")

    monkeypatch.setattr(ExternalOrderDocumentService, "get_order", get_order)
    args = {"order_id": 23, "idempotency_key": "order-external-doc-1",
            "payload": {"document_type": "act", "number": "TEST-1", "document_date": "2026-11-20"}}
    request = {"name": "upload_order_document", "arguments": args}
    denied = (await _rpc(client, "tools/call", request, token="token-two")).json()["result"]
    assert denied["structuredContent"]["error"]["code"] == "insufficient_scope"
    assert not checked
    access["token-two"].add(ORDER_DOCS_UPLOAD_SCOPE)
    no_access = (await _rpc(client, "tools/call", request, token="token-two")).json()["result"]
    assert no_access["structuredContent"]["error"]["code"] == "not_found"
    assert "manager_url" not in no_access["structuredContent"]
    assert checked == [(2, 23)]


@pytest.mark.asyncio
async def test_document_file_delivery_error_returns_verified_upload_link_without_document_id(mcp_client, monkeypatch):
    client, access, _, _ = mcp_client
    access["token-one"].add(ORDER_DOCS_UPLOAD_SCOPE)
    args = {"order_id": 23, "idempotency_key": "order-external-doc-2",
            "payload": {"number": "TEST-2", "document_date": "2026-11-20"}}

    async def get_order(session, scope, order_id):
        assert (scope.tenant_id, order_id) == (1, 23)

    async def create(session, *, source, actor, order_id, payload, idempotency_key):
        assert payload.document_type == "contract"
        assert source.fingerprint() == {"file_id": "file_test", "filename": "", "mime_type": ""}
        await source.loader()
        pytest.fail("Delivery failure must abort the domain command")

    async def unavailable(file):
        raise ConnectorFileUnavailable("temporary upload unavailable")

    monkeypatch.setattr(ExternalOrderDocumentService, "get_order", get_order)
    monkeypatch.setattr(ExternalOrderDocumentService, "create", create)
    monkeypatch.setattr(ConnectorFileService, "download_attachment", unavailable)
    for extra, code in [({}, "file_required"), ({"file": {
        "file_id": "file_test", "download_url": "https://delivery.example/private?signature=hidden",
    }}, "retryable")]:
        result = (await _rpc(client, "tools/call", {
            "name": "register_external_order_contract", "arguments": {**args, **extra},
        })).json()["result"]
        assert result["isError"]
        details = result["structuredContent"]
        assert details["error"]["code"] == code
        assert "document_id" not in details and "signature" not in str(details)
        url = urlsplit(details["manager_url"])
        assert url.path.endswith("/orders/23")
        assert parse_qs(url.query) == {
            "section": ["documents"], "action": ["uploadExternalDocument"], "documentType": ["contract"],
        }


@pytest.mark.asyncio
async def test_attachment_returns_actual_file_version_and_maps_stale_conflict(mcp_client, monkeypatch):
    client, access, _, _ = mcp_client
    access["token-one"].add(ORDER_DOCS_UPLOAD_SCOPE)

    async def get_order(session, scope, order_id):
        assert order_id == 23

    async def get_document(session, scope, document_id):
        return SimpleNamespace(id=document_id, order_id=23, doc_type="act",
                               origin="external_upload", external_status="received", proposal_id=None)

    async def attach(session, *, document_id, file_role, expected_version, source, **kwargs):
        assert document_id == 991 and file_role == "signed_copy"
        if expected_version == 0:
            raise ExternalDocumentVersionConflictError("Version mismatch")
        assert expected_version == 1
        assert source.fingerprint() == {"file_id": "file_test", "filename": "signed.pdf", "mime_type": "application/pdf"}
        return SimpleNamespace(value=ExternalDocumentWriteResult(document_id=991, file_version=2), replayed=True)

    monkeypatch.setattr(ExternalOrderDocumentService, "get_order", get_order)
    monkeypatch.setattr(ExternalOrderDocumentService, "get_document", get_document)
    monkeypatch.setattr(ExternalOrderDocumentService, "attach", attach)
    args = {"order_id": 23, "document_id": 991, "file_role": "signed_copy", "expected_version": 0,
            "idempotency_key": "order-external-doc-3",
            "file": {"file_id": "file_test", "download_url": "https://delivery.example/file",
                     "file_name": "signed.pdf", "mime_type": "application/pdf"}}
    request = {"name": "attach_order_document_file", "arguments": args}
    stale = (await _rpc(client, "tools/call", request)).json()["result"]
    assert stale["structuredContent"]["error"]["code"] == "version_conflict"
    args["expected_version"] = 1
    result = (await _rpc(client, "tools/call", request)).json()["result"]
    assert not result["isError"]
    saved = result["structuredContent"]
    assert saved["replayed"] and saved["result"]["file_version"] == 2
    assert saved["result"]["document_id"] == 991
    assert saved["result"]["external_status"] == "received"


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "document_type"), [
    ("prepare_order_technical_act", "technical_inspection_act"),
    ("prepare_order_defect_act", "defect_act"),
])
async def test_diagnostic_document_tool_selects_exact_native_type(mcp_client, monkeypatch, tmp_path, tool_name, document_type):
    client, access, _, _ = mcp_client
    access["token-one"].add("kitlane:contracts:drafts:write")

    async def prepare(session, actor, data, *, template_storage):
        assert [item.equipment_id for item in data.inspections] == [1, 2]
        assert data.document_type == document_type and data.base_document_id == 99
        assert data.issue_date == date(2026, 11, 20)
        return SimpleNamespace(value=OrderTechnicalActPrepared(order_id=23, site_id=77, equipment_ids=[1, 2],
            document_id=100, document_type=document_type, status="draft", revision="current",
            manager_url="https://example.test/orders/23?section=documents&documentId=100"), replayed=False)

    monkeypatch.setattr(OrderTechnicalActService, "prepare", prepare)
    monkeypatch.setattr("services.connector_order_documents.get_private_attachment_storage",
                        lambda: LocalPrivateAttachmentStorage(tmp_path))
    args = {"order_id": 23, "site_id": 77, "expected_site_version": 3, "legal_entity_id": 55,
            "issue_date": "2026-11-20", "base_document_id": 99, "idempotency_key": "order-inspection-act-1",
            "inspections": [{"equipment_id": 1, "expected_version": 9},
                            {"equipment_id": 2, "expected_version": 8}]}
    result = (await _rpc(client, "tools/call", {"name": tool_name, "arguments": args})).json()["result"]
    assert not result["isError"], result
    assert result["structuredContent"]["result"]["document_type"] == document_type
    assert result["structuredContent"]["result"]["status"] == "draft"


@pytest.mark.asyncio
async def test_document_list_returns_revision_for_existing_act_and_upload_link(mcp_client, monkeypatch):
    from datetime import datetime

    from models import OrderDocument
    from modules.documents.application.draft_parameters import draft_revision

    client, _, _, _ = mcp_client
    document = OrderDocument(
        id=991, order_id=23, proposal_id=73, tenant_id=1, doc_type="act", number="ACT-TEST",
        date=datetime(2026, 11, 20), status="issued", scope_meta={"site_ids": [7, 8, 9]},
        render_snapshot={"meta": {"test": True}},
    )
    artifact = SimpleNamespace(id="artifact-id", checksum_sha256="sum", is_authoritative=True)

    async def get_order(session, scope, order_id):
        assert order_id == 23 and scope.tenant_id == 1

    async def document_page(session, *, scope, inputs):
        assert inputs.site_id == 7 and inputs.document_type == "act"
        return [(document, 1)], 3, {document.id: [artifact]}

    monkeypatch.setattr(ExternalOrderDocumentService, "get_order", get_order)
    monkeypatch.setattr("services.connector_order_documents.list_documents", document_page)
    response = (await _rpc(client, "tools/call", {
        "name": "list_order_documents", "arguments": {"order_id": 23, "site_id": 7, "document_type": "act", "limit": 1},
    })).json()["result"]
    assert not response["isError"], response
    content = response["structuredContent"]
    saved = content["items"][0]
    assert saved["origin"] == "native_generated"
    assert saved["status"] == "issued" and saved["file_version"] == 1 and saved["site_ids"] == [7, 8, 9]
    assert saved["revision"] == draft_revision(document, [artifact])
    assert parse_qs(urlsplit(saved["manager_url"]).query)["proposalId"] == ["73"]
    assert content["has_more"] and "action=uploadExternalDocument" in content["upload_manager_url"]


@pytest.mark.asyncio
async def test_completion_mcp_reads_version_then_prepares_same_order_draft(mcp_client, monkeypatch, tmp_path):
    from schemas_order_completion_acts import OrderCompletionActPrepared, OrderCompletionActSource
    from services.connector_order_documents import OrderCompletionActService

    client, access, _, _ = mcp_client
    version = "1" * 64

    async def source(session, actor, data):
        return OrderCompletionActSource(order_id=data.order_id, proposal_id=data.proposal_id, proposal_version=version)

    async def prepare(session, actor, data, *, template_storage):
        assert data.expected_proposal_version == version
        assert data.base_document_id == 99 and data.site_ids == [7, 8, 9]
        assert data.scope_service_line_quantities == {43: 1}
        return SimpleNamespace(value=OrderCompletionActPrepared(order_id=data.order_id, proposal_id=data.proposal_id,
            site_ids=data.site_ids, document_id=991, status="draft", revision="current",
            manager_url="https://example.test/orders/23?section=documents&documentId=991"), replayed=False)

    monkeypatch.setattr(OrderCompletionActService, "source", source)
    monkeypatch.setattr(OrderCompletionActService, "prepare", prepare)
    monkeypatch.setattr("services.connector_order_documents.get_private_attachment_storage",
                        lambda: LocalPrivateAttachmentStorage(tmp_path))
    arguments = {"order_id": 23, "proposal_id": 73}
    version_result = (await _rpc(client, "tools/call", {
        "name": "get_order_completion_act_source", "arguments": arguments,
    })).json()["result"]
    assert not version_result["isError"]
    command = {"name": "prepare_order_completion_act", "arguments": {
        **arguments, "expected_proposal_version": version_result["structuredContent"]["proposal_version"],
        "idempotency_key": "order-completion-act-1", "issue_date": "2026-11-20", "legal_entity_id": 55,
        "base_document_id": 99, "site_ids": [7, 8, 9], "act_terms": {},
        "scope_service_line_ids": [43], "scope_service_line_quantities": {"43": 1},
    }}
    denied = (await _rpc(client, "tools/call", command)).json()["result"]
    assert denied["structuredContent"]["error"]["code"] == "insufficient_scope"
    access["token-one"].add("kitlane:contracts:drafts:write")
    result = (await _rpc(client, "tools/call", command)).json()["result"]
    assert not result["isError"], result
    assert result["structuredContent"]["result"]["document_id"] == 991
    assert result["structuredContent"]["result"]["order_id"] == 23
