"""Mail MCP transport: separate rights, exact saved versions and no forged consent."""

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from schemas_mail import MailMessageResponse
from services.connector_file_service import ConnectorFileService
from services.connector_mcp_tools import TOOLS
from services.mail_workspace_service import MailWorkspaceService
from services.mail_workspace_access import MailStateConflictError, MailVersionConflictError
from tests.unit.test_connector_mcp_transport import _rpc, mcp_client


def mail(**changes):
    return MailMessageResponse(
        **{
            "id": 17, "version": 4, "status": "draft", "folder": "drafts",
            "sender_email": "company@example.org", "sender_name": "Company",
            "to": ["supplier@example.org"], "cc": ["accounting@example.org"],
            "bcc": ["manager@example.org"], "subject": "ebm-papst A2E200-AI38-01",
            "body_text": "Полный текст запроса\nВторая строка",
            "attachments": [{"id": 3, "filename": "specification.pdf", "size": 100,
                             "sha256": "a" * 64, "available": True}],
            "manager_url": "https://api.mvn.by/manager/mail?messageId=17",
            "created_at": datetime.now(timezone.utc), **changes,
        }
    )


def test_mail_discovery_annotations_scopes_and_file_transport():
    read = TOOLS["preview_mail_draft"].definition().model_dump(by_alias=True)
    assert read["annotations"]["readOnlyHint"] is True
    assert read["_meta"]["securitySchemes"][0]["scopes"] == ["kitlane:read", "kitlane:mail:read"]
    write = TOOLS["create_mail_draft"].definition().model_dump(by_alias=True)
    assert write["annotations"]["readOnlyHint"] is False
    assert write["_meta"]["securitySchemes"][0]["scopes"] == ["kitlane:read", "kitlane:mail:drafts:write"]
    send = TOOLS["send_mail_draft"].definition().model_dump(by_alias=True)
    assert send["annotations"]["openWorldHint"] is True
    assert send["annotations"]["destructiveHint"] is True
    assert send["annotations"]["readOnlyHint"] is False
    assert set(send["inputSchema"]["properties"]) == {"draft_id", "expected_version", "idempotency_key"}
    assert send["inputSchema"]["additionalProperties"] is False
    upload = TOOLS["upload_mail_draft_attachment"].definition().model_dump(by_alias=True)
    assert upload["_meta"]["openai/fileParams"] == ["file"]
    assert set(upload["inputSchema"]["$defs"]["OpenAIFile"]["required"]) == {"download_url", "file_id"}
    assert not {"confirm_mail_draft", "approve_mail_draft"} & TOOLS.keys()


@pytest.mark.asyncio
async def test_incomplete_draft_scope_and_actor_do_not_send(mcp_client, monkeypatch):
    client, access, checks, _ = mcp_client
    recorded = []

    async def create(session, *, actor, payload, idempotency_key):
        recorded.append((actor, payload.model_dump(), idempotency_key))
        return SimpleNamespace(value=mail(to=[], cc=[], bcc=[], subject="", body_text=""), replayed=False)

    async def forbidden_send(*args, **kwargs):
        pytest.fail("Saving a draft must never send mail")

    monkeypatch.setattr(MailWorkspaceService, "create_draft", create)
    monkeypatch.setattr(MailWorkspaceService, "send", forbidden_send)
    arguments = {"idempotency_key": "mail-empty-draft-0001", "payload": {}}
    denied = (await _rpc(client, "tools/call", {"name": "create_mail_draft", "arguments": arguments})).json()["result"]
    assert denied["isError"] and denied["structuredContent"]["error"]["code"] == "insufficient_scope"
    assert not recorded
    access["token-one"].add("kitlane:mail:drafts:write")
    result = (await _rpc(client, "tools/call", {"name": "create_mail_draft", "arguments": arguments})).json()["result"]
    assert not result["isError"]
    saved = result["structuredContent"]["result"]
    assert saved["status"] == "draft" and saved["to"] == []
    assert recorded[0][0].channel == "chatgpt" and recorded[0][0].staff_user_id == 1
    assert recorded[0][1]["order_id"] is None and recorded[0][1]["customer_id"] is None
    assert checks[-1] == ("token-one", "kitlane:mail:drafts:write")


@pytest.mark.asyncio
async def test_maximum_escaped_mail_body_is_accepted_without_truncation(mcp_client, monkeypatch):
    import json
    client, access, _, _ = mcp_client
    access["token-one"].add("kitlane:mail:drafts:write")
    body_text = "🙂" * 100_000
    async def create(session, *, actor, payload, idempotency_key):
        assert payload.body_text == body_text
        return SimpleNamespace(value=mail(body_text=body_text), replayed=False)
    monkeypatch.setattr(MailWorkspaceService, "create_draft", create)
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "create_mail_draft", "arguments": {"idempotency_key": "mail-unicode-body-0001",
                                                   "payload": {"body_text": body_text}},
    }}, ensure_ascii=True).encode()
    assert len(body) > 1024 * 1024
    result = (await client.post("/api/connector/mcp", content=body,
                               headers={"Content-Type": "application/json"})).json()["result"]
    assert not result["isError"] and result["structuredContent"]["result"]["body_text"] == body_text


@pytest.mark.asyncio
async def test_full_preview_requires_new_mail_read_scope(mcp_client, monkeypatch):
    client, access, _, _ = mcp_client
    async def preview(session, *, actor, draft_id):
        assert draft_id == 17
        return mail()
    monkeypatch.setattr(MailWorkspaceService, "preview", preview)
    params = {"name": "preview_mail_draft", "arguments": {"draft_id": 17}}
    denied = (await _rpc(client, "tools/call", params)).json()["result"]
    assert denied["structuredContent"]["error"]["code"] == "insufficient_scope"
    access["token-one"].add("kitlane:mail:read")
    saved = (await _rpc(client, "tools/call", params)).json()["result"]["structuredContent"]
    assert saved["to"] == ["supplier@example.org"]
    assert saved["cc"] and saved["bcc"]
    assert saved["body_text"] == "Полный текст запроса\nВторая строка"
    assert saved["attachments"][0]["filename"] == "specification.pdf"
    assert saved["version"] == 4 and saved["manager_url"]


@pytest.mark.asyncio
async def test_send_rejects_forged_approval_and_passes_only_saved_version(mcp_client, monkeypatch):
    client, access, _, _ = mcp_client
    recorded = []
    async def send(session, *, actor, draft_id, payload, idempotency_key, authorize_before_send=None):
        recorded.append((draft_id, payload.model_dump(), idempotency_key))
        raise HTTPException(409, "Approve this exact version in Manager before sending")
    monkeypatch.setattr(MailWorkspaceService, "send", send)
    arguments = {"draft_id": 17, "expected_version": 4, "idempotency_key": "mail-send-current-0001"}
    access["token-one"].add("kitlane:mail:drafts:write")
    denied = (await _rpc(client, "tools/call", {"name": "send_mail_draft", "arguments": arguments})).json()["result"]
    assert denied["structuredContent"]["error"]["code"] == "insufficient_scope"
    assert not recorded
    access["token-one"].add("kitlane:mail:send")
    for extra in ({"confirmed": True}, {"body_text": "Changed"}, {"actor": {"channel": "manager"}}):
        forged = (await _rpc(client, "tools/call", {"name": "send_mail_draft", "arguments": {**arguments, **extra}})).json()["result"]
        assert forged["isError"]
    assert not recorded
    blocked = (await _rpc(client, "tools/call", {"name": "send_mail_draft", "arguments": arguments})).json()["result"]
    assert blocked["isError"] and "Manager" in str(blocked)
    assert recorded == [(17, {"expected_version": 4}, "mail-send-current-0001")]


@pytest.mark.asyncio
async def test_mail_send_rechecks_connector_scope_after_async_claim(mcp_client, monkeypatch):
    client, access, checks, _ = mcp_client
    access["token-one"].add("kitlane:mail:send")
    smtp_calls = []
    async def send(session, *, actor, draft_id, payload, idempotency_key, authorize_before_send):
        # Emulate grant withdrawal after the durable send claim. The shared
        # sender must invoke this callback before touching the transport.
        access["token-one"].discard("kitlane:mail:send")
        await authorize_before_send()
        smtp_calls.append(True)
        return SimpleNamespace(value=mail(status="sent"), replayed=False)
    monkeypatch.setattr(MailWorkspaceService, "send", send)
    result = (await _rpc(client, "tools/call", {"name": "send_mail_draft", "arguments": {
        "draft_id": 17, "expected_version": 4, "idempotency_key": "mail-send-revoked-0001",
    }})).json()["result"]
    assert result["isError"] and result["structuredContent"]["error"]["code"] == "insufficient_scope"
    assert not smtp_calls
    assert checks[-1] == ("token-one", "kitlane:mail:send")


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict,code,current", [
    (MailVersionConflictError(5), "version_conflict", 5),
    (MailStateConflictError("Подтвердите письмо в Manager"), "mail_state_conflict", 4),
])
async def test_saved_draft_conflicts_return_version_and_manager_link(mcp_client, monkeypatch, conflict, code, current):
    client, access, _, _ = mcp_client
    access["token-one"].add("kitlane:mail:send")
    async def send(*args, **kwargs):
        raise conflict
    monkeypatch.setattr(MailWorkspaceService, "send", send)
    result = (await _rpc(client, "tools/call", {"name": "send_mail_draft", "arguments": {
        "draft_id": 17, "expected_version": 4, "idempotency_key": "mail-send-conflict-0001",
    }})).json()["result"]
    assert result["isError"]
    saved = result["structuredContent"]
    assert saved["error"]["code"] == code and saved["error"]["status"] == 409
    assert saved["id"] == 17 and saved["version"] == current and saved["status"] == "conflict"
    assert "emailId=17" in saved["manager_url"]


@pytest.mark.asyncio
async def test_mail_attachment_transport_unconfigured_never_mutates(mcp_client, monkeypatch):
    from core.config import settings
    client, access, _, _ = mcp_client
    access["token-one"].add("kitlane:mail:drafts:write")
    monkeypatch.setattr(settings, "CONNECTOR_CHATGPT_FILE_HOSTS", [])
    async def forbidden_upload(*args, **kwargs):
        pytest.fail("Unavailable transport must not save a fake attachment")
    monkeypatch.setattr(MailWorkspaceService, "upload_attachment", forbidden_upload)
    arguments = {"draft_id": 17, "expected_version": 4, "idempotency_key": "mail-attachment-0001",
                 "file": {"file_id": "file-123", "download_url": "https://files.example/private-spec.pdf?signature=private-secret"}}
    result = (await _rpc(client, "tools/call", {"name": "upload_mail_draft_attachment", "arguments": arguments})).json()["result"]
    assert result["structuredContent"]["error"]["code"] == "invalid_file"
    assert "Manager" in str(result)
    assert "delivery hostname: files.example" in str(result)
    assert not any(secret in str(result) for secret in ("https://", "private-spec", "signature", "private-secret", "file-123"))


@pytest.mark.asyncio
async def test_attachment_loader_is_deferred_with_stable_source_identity(mcp_client, monkeypatch):
    from core.config import settings
    client, access, _, _ = mcp_client
    access["token-one"].add("kitlane:mail:drafts:write")
    monkeypatch.setattr(settings, "CONNECTOR_CHATGPT_FILE_HOSTS", ["files.example"])
    downloaded = []
    recorded = []
    async def download(file):
        downloaded.append(file.download_url)
        return b"private PDF bytes"
    async def upload(session, *, actor, draft_id, expected_version, idempotency_key,
                     filename, mime_type, source_file_id, loader):
        recorded.append((draft_id, expected_version, filename, mime_type, source_file_id))
        if len(recorded) == 1:
            assert not downloaded
            assert await loader() == b"private PDF bytes"
        return SimpleNamespace(value=mail(version=5), replayed=len(recorded) > 1)
    monkeypatch.setattr(ConnectorFileService, "download_attachment", download)
    monkeypatch.setattr(MailWorkspaceService, "upload_attachment", upload)
    arguments = {"draft_id": 17, "expected_version": 4, "idempotency_key": "mail-attachment-0001",
                 "file": {"file_id": "file-123", "download_url": "https://files.example/spec.pdf?first",
                          "file_name": "spec.pdf", "mime_type": "application/pdf"}}
    first = (await _rpc(client, "tools/call", {"name": "upload_mail_draft_attachment", "arguments": arguments})).json()["result"]
    arguments["file"]["download_url"] = "https://files.example/spec.pdf?refreshed"
    retry = (await _rpc(client, "tools/call", {"name": "upload_mail_draft_attachment", "arguments": arguments})).json()["result"]
    assert not first["isError"] and retry["structuredContent"]["replayed"] is True
    assert len(downloaded) == 1 and recorded[0] == recorded[1]
