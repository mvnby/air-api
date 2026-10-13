"""Thin MCP adapter over the same saved mail commands used by Manager."""

from schemas_mail import MailVersionPayload
from services.connector_file_service import ConnectorFileService
from services.mail_workspace_service import MailWorkspaceService


class ConnectorMailService:
    @staticmethod
    async def read(session, actor, name, inputs):
        if name == "list_mail_accounts":
            return await MailWorkspaceService.get_accounts(session, actor=actor)
        if name == "search_mail":
            return await MailWorkspaceService.list_messages(
                session, actor=actor, **inputs.model_dump()
            )
        if name in {"get_mail", "get_mail_send_result"}:
            return await MailWorkspaceService.get_message(
                session, actor=actor, message_id=inputs.message_id
            )
        if name == "preview_mail_draft":
            return await MailWorkspaceService.preview(
                session, actor=actor, draft_id=inputs.draft_id
            )
        raise ValueError("Unknown mail read")

    @staticmethod
    async def write(session, actor, name, inputs, *, authorize_before_send=None):
        common = {"actor": actor, "idempotency_key": inputs.idempotency_key}
        if name == "create_mail_draft":
            return await MailWorkspaceService.create_draft(
                session, payload=inputs.payload, **common
            )
        common["draft_id"] = inputs.draft_id
        if name == "update_mail_draft":
            return await MailWorkspaceService.update_draft(
                session, payload=inputs.payload, **common
            )
        if name == "upload_mail_draft_attachment":
            # No arbitrary URL or local sandbox path is accepted. The temporary
            # link stays outside command fingerprints, receipts and audit.
            ConnectorFileService.validate_source(inputs.file)
            filename = inputs.file.file_name or f"{inputs.file.file_id}.bin"
            mime_type = inputs.file.mime_type or "application/octet-stream"

            async def loader():
                return await ConnectorFileService.download_attachment(inputs.file)

            return await MailWorkspaceService.upload_attachment(
                session, expected_version=inputs.expected_version,
                filename=filename, mime_type=mime_type,
                source_file_id=inputs.file.file_id, loader=loader, **common,
            )
        if name in {"delete_mail_draft", "send_mail_draft"}:
            action = "delete_draft" if name == "delete_mail_draft" else "send"
            if name == "send_mail_draft":
                common["authorize_before_send"] = authorize_before_send
            return await getattr(MailWorkspaceService, action)(
                session, payload=MailVersionPayload(expected_version=inputs.expected_version),
                **common,
            )
        raise ValueError("Unknown mail write")
