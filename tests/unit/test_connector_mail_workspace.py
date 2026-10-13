"""Real shared mail commands across MCP and Manager, with substituted SMTP."""

from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from mail_workspace_test_support import _actor, mail_db_engine, smtp_settings
from schemas_mail import MailConfirmPayload, MailDraftUpdatePayload
from services.connector_file_service import ConnectorFileService
from services.connector_mcp_tools import TOOLS, execute_tool
from services.mail_smtp_service import MailSmtpService
from services.mail_workspace_access import MailStateConflictError, MailVersionConflictError
from services.mail_workspace_service import MailWorkspaceService as Mail


async def call(session, actor, name, arguments):
    return await execute_tool(session, actor, TOOLS[name], arguments)


@pytest.mark.asyncio
async def test_mcp_supplier_draft_manager_edit_approval_exact_send_and_replay(mail_db_engine, monkeypatch):
    monkeypatch.setattr(settings, "CONNECTOR_CHATGPT_FILE_HOSTS", ["files.example"])
    frozen_file = b"%PDF-1.4 frozen ebm-papst specification"
    downloads, sent = [], []
    async def download(file):
        downloads.append(file.file_id)
        return frozen_file
    monkeypatch.setattr(ConnectorFileService, "download_attachment", download)
    monkeypatch.setattr(MailSmtpService, "send_message", staticmethod(sent.append))

    async with AsyncSession(mail_db_engine, expire_on_commit=False) as session:
        manager = await _actor(session)
        chatgpt = replace(manager, channel="chatgpt")
        created = await call(session, chatgpt, "create_mail_draft", {
            "idempotency_key": "mcp-supplier-draft-0001", "payload": {
                "to": ["supplier@example.test"], "subject": "ebm-papst A2E200-AI38-01",
                "body_text": "Просим сообщить цену вентилятора ebm-papst A2E200-AI38-01.",
            },
        })
        saved = created["result"]
        assert saved["status"] == "draft" and saved["order_id"] is saved["customer_id"] is None
        upload = {"draft_id": saved["id"], "expected_version": saved["version"],
                  "idempotency_key": "mcp-supplier-file-0001", "file": {
                      "file_id": "file-specification123", "download_url": "https://files.example/spec.pdf?first",
                      "file_name": "specification.pdf", "mime_type": "application/pdf",
                  }}
        uploaded = await call(session, chatgpt, "upload_mail_draft_attachment", upload)
        upload["file"]["download_url"] = "https://files.example/spec.pdf?refreshed"
        replay_file = await call(session, chatgpt, "upload_mail_draft_attachment", upload)
        assert replay_file["replayed"] and len(downloads) == 1
        current = await Mail.get_message(session, actor=manager, message_id=saved["id"])
        assert current.attachments[0].sha256 == uploaded["result"]["attachments"][0]["sha256"]
        full_text = "Просим сообщить цену и срок поставки ebm-papst A2E200-AI38-01.\nВложена спецификация."
        edited = await Mail.update_draft(session, actor=manager, draft_id=current.id,
            payload=MailDraftUpdatePayload(expected_version=current.version, body_text=full_text),
            idempotency_key="manager-supplier-edit-0001")
        preview = await call(session, chatgpt, "preview_mail_draft", {"draft_id": current.id})
        assert preview["body_text"] == full_text and preview["version"] == edited.value.version
        assert preview["attachments"][0]["filename"] == "specification.pdf"
        assert not sent
        send_arguments = {"draft_id": current.id, "expected_version": preview["version"],
                          "idempotency_key": "mcp-supplier-send-0001"}
        with pytest.raises(MailStateConflictError, match="Manager"):
            await call(session, chatgpt, "send_mail_draft", send_arguments)
        await Mail.confirm(session, actor=manager, draft_id=current.id,
            payload=MailConfirmPayload(expected_version=preview["version"], content_hash=preview["content_hash"]),
            idempotency_key="manager-supplier-confirm-0001")
        result = await call(session, chatgpt, "send_mail_draft", send_arguments)
        replay = await call(session, chatgpt, "send_mail_draft", send_arguments)
        other_key = await call(session, chatgpt, "send_mail_draft", {
            **send_arguments, "idempotency_key": "mcp-supplier-second-key-0001",
        })
        assert result["result"]["status"] == "sent" and replay["replayed"]
        assert other_key["result"]["status"] == "sent" and len(sent) == 1
        assert sent[0].get_body(preferencelist=("plain",)).get_content().strip() == full_text
        assert list(sent[0].iter_attachments())[0].get_payload(decode=True) == frozen_file
        status = await call(session, chatgpt, "get_mail_send_result", {"message_id": current.id})
        assert status["version"] == preview["version"] and status["status"] == "sent"
        assert status["message_id"] == sent[0]["Message-ID"] and status["manager_url"]


@pytest.mark.asyncio
async def test_manager_edit_invalidates_mcp_saved_version_and_approval(mail_db_engine):
    async with AsyncSession(mail_db_engine, expire_on_commit=False) as session:
        manager = await _actor(session)
        chatgpt = replace(manager, channel="chatgpt")
        created = await call(session, chatgpt, "create_mail_draft", {
            "idempotency_key": "mcp-stale-draft-0001", "payload": {
                "to": ["supplier@example.test"], "subject": "Supplier request", "body_text": "Original text",
            },
        })
        draft = await Mail.get_message(session, actor=manager, message_id=created["result"]["id"])
        await Mail.confirm(session, actor=manager, draft_id=draft.id,
            payload=MailConfirmPayload(expected_version=draft.version, content_hash=draft.content_hash),
            idempotency_key="manager-stale-confirm-0001")
        changed = await Mail.update_draft(session, actor=manager, draft_id=draft.id,
            payload=MailDraftUpdatePayload(expected_version=draft.version, to=["another@example.test"]),
            idempotency_key="manager-stale-change-0001")
        assert changed.value.confirmed_version is None
        with pytest.raises(MailVersionConflictError):
            await call(session, chatgpt, "send_mail_draft", {
                "draft_id": draft.id, "expected_version": draft.version,
                "idempotency_key": "mcp-stale-send-0001",
            })
        with pytest.raises(MailStateConflictError, match="подтвердите"):
            await call(session, chatgpt, "send_mail_draft", {
                "draft_id": draft.id, "expected_version": changed.value.version,
                "idempotency_key": "mcp-unapproved-send-0001",
            })
