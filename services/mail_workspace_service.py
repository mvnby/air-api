"""Saved drafts and private file snapshots shared by Manager and MCP."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.config import settings
from crud.mail_workspace import MailWorkspaceDAO
from models import OutgoingEmail
from models.mail_workspace import MailAttachmentSnapshot
from schemas_mail import (
    MailConfirmPayload, MailDraftCreatePayload, MailDraftUpdatePayload,
    MailMessageListResponse, MailMessageResponse, MailVersionPayload,
)
from services.authenticated_command_service import AuthenticatedCommandService
from services.mail_smtp_service import MailAttachment, MAX_ORDER_EMAIL_ATTACHMENT_BYTES, MAX_ORDER_EMAIL_TOTAL_ATTACHMENT_BYTES
from services.mail_workspace_access import (
    MailNotFoundError, MailStateConflictError, MailVersionConflictError, MailWorkspaceAccess,
)
from services.public_write_idempotency_service import PublicWriteCommandOutcome, PublicWriteCommandResponse


class MailWorkspaceService:
    RESPONSE_MAX_BYTES = 768 * 1024

    @staticmethod
    def manager_url(email_id: int) -> str:
        return f"{settings.MANAGER_BASE_URL.rstrip('/')}/mail?emailId={email_id}"

    @staticmethod
    def _hash(row: OutgoingEmail, snapshots: list[MailAttachmentSnapshot]) -> str:
        content = {
            "id": row.id, "version": row.version, "account_id": row.account_id,
            "sender_email": row.from_email, "sender_name": row.from_name,
            "to": row.recipient_email, "cc": row.cc_emails, "bcc": row.bcc_emails,
            "subject": row.subject, "body_text": row.body_text, "body_html": row.body_html,
            "reply_to": row.reply_to, "in_reply_to": row.in_reply_to, "references": row.references,
            "order_id": row.order_id, "customer_id": row.customer_id,
            "files": [{"id": item.id, "filename": item.filename, "mime_type": item.mime_type,
                       "size": item.size, "sha256": item.sha256} for item in snapshots],
        }
        return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    @classmethod
    async def _project(cls, session: AsyncSession, row: OutgoingEmail, actor: CommandActor, *, snapshots=None, summary=False, body_preview="") -> MailMessageResponse:
        if snapshots is None:
            snapshots = await MailWorkspaceDAO.attachments(session, int(row.id), actor.tenant_scope.tenant_id, include_content=False)
        attachments = [{
            "id": item.id, "filename": item.filename, "mime_type": item.mime_type,
            "size": item.size, "sha256": item.sha256, "available": True,
            "download_url": f"/api/manager/mail/drafts/{row.id}/attachments/{item.id}",
        } for item in snapshots]
        # Existing metadata-only journal records remain readable; never claim their bytes exist.
        if not snapshots:
            attachments = [{
                "filename": str(item.get("filename") or "Вложение"),
                "mime_type": str(item.get("mime_type") or "application/octet-stream"),
                "size": int(item.get("size") or 0), "available": False,
            } for item in row.attachments or []]
        return MailMessageResponse(
            id=int(row.id), version=row.version, status=row.status,
            folder="drafts" if row.status == "draft" else "outbox", account_id=row.account_id,
            sender_email=row.from_email, sender_name=row.from_name,
            to=[item.strip() for item in row.recipient_email.split(",") if item.strip()],
            cc=row.cc_emails or [], bcc=row.bcc_emails or [], subject=row.subject,
            body_text=(body_preview or "") if summary else row.body_text or cls._html_to_text(row.body_html), attachments=attachments,
            in_reply_to=row.in_reply_to, references=row.references, delivery_projection_pending=row.delivery_projection_pending,
            order_id=row.order_id, customer_id=row.customer_id,
            manager_url=cls.manager_url(int(row.id)), error=row.error,
            created_at=row.created_at, updated_at=row.updated_at, sent_at=row.sent_at,
            confirmed_version=row.confirmed_version, content_hash=None if summary else cls._hash(row, snapshots),
            message_id=(f"<kitlane-{row.id}-{row.send_token}@{row.from_email.split('@')[-1]}>"
                if row.send_token and row.from_email else None),
        )

    @classmethod
    async def _get(cls, session: AsyncSession, actor: CommandActor, email_id: int, *, lock: bool = False):
        await MailWorkspaceAccess.require_actor(session, actor)
        row = await MailWorkspaceDAO.get(session, email_id, actor.tenant_scope, lock=lock)
        if row is None:
            raise MailNotFoundError("Письмо не найдено")
        await MailWorkspaceAccess.validate_links(session, actor, order_id=row.order_id, customer_id=row.customer_id)
        return row

    @staticmethod
    def _require_draft(row: OutgoingEmail, expected_version: int):
        if row.version != expected_version:
            raise MailVersionConflictError(row.version)
        if row.status != "draft":
            raise MailStateConflictError("История отправки неизменяема. Создайте новый черновик")

    @staticmethod
    def _changed(row: OutgoingEmail):
        row.version += 1
        row.updated_at = datetime.now()
        row.confirmed_version = None
        row.confirmed_hash = None
        row.confirmed_by_staff_user_id = None
        row.confirmed_at = None

    @classmethod
    async def _command(cls, session, actor, name, key, payload, operation):
        await MailWorkspaceAccess.require_actor(session, actor, write=True)
        outcome = await AuthenticatedCommandService.execute(
            session, actor=actor, command_name=f"mail.{name}", idempotency_key=key,
            payload=payload, response_model=MailMessageResponse, operation=operation,
        )
        if outcome.replayed:
            await MailWorkspaceAccess.validate_links(session, actor,
                order_id=outcome.value.order_id, customer_id=outcome.value.customer_id)
            if outcome.value.status != "deleted":
                await cls._get(session, actor, outcome.value.id)
        return outcome

    @classmethod
    async def _result(cls, session, actor, row, *, status_code=200):
        await session.flush()
        return PublicWriteCommandResponse(
            value=await cls._project(session, row, actor), status_code=status_code,
            resource_type="outgoing_email", resource_id=int(row.id), response_max_bytes=cls.RESPONSE_MAX_BYTES,
        )

    @classmethod
    async def get_accounts(cls, session, *, actor):
        return await MailWorkspaceAccess.accounts(session, actor)

    @classmethod
    async def get_message(cls, session, *, actor, message_id: int):
        if message_id < 0:
            from services.incoming_mail_service import IncomingMailService
            return await IncomingMailService.get_message(session, actor=actor, email_id=message_id)
        row = await cls._get(session, actor, message_id)
        from services.mail_workspace_delivery import MailWorkspaceDelivery
        if await MailWorkspaceDelivery.recover_stale_claim(session, row, actor=actor):
            await session.commit()
        if row.status == "sent" and row.delivery_projection_pending:
            await MailWorkspaceDelivery.recover_projection(session, actor=actor, email_id=message_id)
            row = await cls._get(session, actor, message_id)
        return await cls._project(session, row, actor)

    @classmethod
    async def list_messages(cls, session, *, actor, folder="outbox", q=None, status=None, order_id=None,
                            customer_id=None, page=1, limit=50):
        await MailWorkspaceAccess.require_actor(session, actor)
        if folder not in {"inbox", "outbox", "drafts"} or not 1 <= limit <= 100 or page < 1:
            raise ValueError("Недопустимая папка или размер страницы")
        await MailWorkspaceAccess.validate_links(session, actor, order_id=order_id, customer_id=customer_id)
        if folder == "inbox":
            from services.incoming_mail_service import IncomingMailService
            items, total = await IncomingMailService.list_messages(
                session, actor=actor, page=page, limit=limit, q=q, order_id=order_id, customer_id=customer_id, status=status
            )
        else:
            rows, total = await MailWorkspaceDAO.list(session, actor.tenant_scope, folder=folder, status=status,
                q=q, order_id=order_id, customer_id=customer_id, page=page, limit=limit)
            snapshots = await MailWorkspaceDAO.attachments_by_email(session, [int(row.id) for row, _ in rows], actor.tenant_scope.tenant_id)
            items = [await cls._project(session, row, actor, snapshots=snapshots[int(row.id)], summary=True, body_preview=preview) for row, preview in rows]
        return MailMessageListResponse(items=items, total=total, page=page, limit=limit)

    @classmethod
    async def create_draft(cls, session, *, actor, payload: MailDraftCreatePayload, idempotency_key):
        async def operation():
            account = await MailWorkspaceAccess.require_account(session, actor, payload.account_id)
            await MailWorkspaceAccess.validate_links(session, actor, order_id=payload.order_id, customer_id=payload.customer_id)
            row = OutgoingEmail(
                tenant_id=actor.tenant_scope.tenant_id, storefront_id=actor.tenant_scope.storefront_id,
                account_id=account.id, version=1, status="draft", from_email=account.email,
                from_name=account.name, created_by_staff_user_id=actor.staff_user_id,
                recipient_email=", ".join(payload.to), cc_emails=payload.cc, bcc_emails=payload.bcc,
                subject=payload.subject, body_text=payload.body_text, in_reply_to=payload.in_reply_to, references=payload.references, order_id=payload.order_id,
                customer_id=payload.customer_id,
            )
            session.add(row)
            return await cls._result(session, actor, row, status_code=201)
        return await cls._command(session, actor, "draft.create", idempotency_key, payload, operation)

    @classmethod
    async def update_draft(cls, session, *, actor, draft_id, payload: MailDraftUpdatePayload, idempotency_key):
        async def operation():
            row = await cls._get(session, actor, draft_id, lock=True)
            cls._require_draft(row, payload.expected_version)
            data = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
            for field in ("account_id", "to", "cc", "bcc", "subject", "body_text"):
                if field in data and data[field] is None:
                    raise ValueError(f"Поле {field} не может быть null")
            account = await MailWorkspaceAccess.require_account(session, actor, data.get("account_id", row.account_id))
            await MailWorkspaceAccess.validate_links(session, actor,
                order_id=data.get("order_id", row.order_id), customer_id=data.get("customer_id", row.customer_id))
            for field, value in data.items():
                target = {"to": "recipient_email", "cc": "cc_emails", "bcc": "bcc_emails"}.get(field, field)
                setattr(row, target, ", ".join(value) if field == "to" else value)
            if "body_text" in data:
                row.body_html = None
            row.from_email, row.from_name = account.email, account.name
            cls._changed(row)
            return await cls._result(session, actor, row)
        return await cls._command(session, actor, "draft.update", idempotency_key,
            {"draft_id": draft_id, **payload.model_dump(exclude_unset=True)}, operation)

    @classmethod
    async def delete_draft(cls, session, *, actor, draft_id, payload: MailVersionPayload, idempotency_key):
        async def operation():
            row = await cls._get(session, actor, draft_id, lock=True)
            cls._require_draft(row, payload.expected_version)
            result = await cls._result(session, actor, row)
            for item in await MailWorkspaceDAO.attachments(session, draft_id, actor.tenant_scope.tenant_id):
                await session.delete(item)
            await session.delete(row)
            return PublicWriteCommandResponse(value=result.value.model_copy(update={"status": "deleted"}),
                resource_type=result.resource_type, resource_id=result.resource_id, response_max_bytes=cls.RESPONSE_MAX_BYTES)
        return await cls._command(session, actor, "draft.delete", idempotency_key,
            {"draft_id": draft_id, "expected_version": payload.expected_version}, operation)

    @classmethod
    def _attachment(cls, *, actor, row, filename: str, mime_type: str, content: bytes, metadata=None):
        filename = filename.replace("\\", "/").split("/")[-1].strip()
        if not filename or any(char in filename for char in "\r\n\x00") or len(filename) > 255:
            raise ValueError("Недопустимое имя файла")
        if not content or len(content) > MAX_ORDER_EMAIL_ATTACHMENT_BYTES:
            raise ValueError("Файл должен быть непустым и не больше 10 МБ")
        if "/" not in mime_type or any(char in mime_type for char in "\r\n\x00") or len(mime_type) > 127:
            mime_type = "application/octet-stream"
        return MailAttachmentSnapshot(
            tenant_id=actor.tenant_scope.tenant_id, email_id=int(row.id), filename=filename,
            mime_type=mime_type, size=len(content), sha256=hashlib.sha256(content).hexdigest(),
            content=content, source_metadata=metadata or {},
        )

    @classmethod
    async def _sync_metadata(cls, session, actor, row):
        snapshots = await MailWorkspaceDAO.attachments(session, int(row.id), actor.tenant_scope.tenant_id)
        row.attachments = [{**item.source_metadata, "snapshot_id": item.id,
            "filename": item.filename, "mime_type": item.mime_type, "size": item.size,
            "sha256": item.sha256} for item in snapshots]

    @classmethod
    async def upload_attachment(cls, session, *, actor, draft_id, expected_version, idempotency_key,
                                filename, mime_type="application/octet-stream", content=None,
                                source_file_id=None, loader: Callable[[], Awaitable[bytes]] | None = None):
        command = {"draft_id": draft_id, "expected_version": expected_version, "filename": filename, "mime_type": mime_type}
        if source_file_id:
            command["source_file_id"] = source_file_id
        elif content is not None:
            command["sha256"] = hashlib.sha256(content).hexdigest()
        else:
            raise ValueError("Содержимое файла не передано")
        async def operation():
            row = await cls._get(session, actor, draft_id, lock=True)
            cls._require_draft(row, expected_version)
            await MailWorkspaceAccess.require_account(session, actor, row.account_id)
            files = await MailWorkspaceDAO.attachments(session, draft_id, actor.tenant_scope.tenant_id)
            value = content if content is not None else await loader() if loader else None
            if not isinstance(value, bytes):
                raise ValueError("Содержимое файла не передано")
            if len(files) >= 10 or sum(item.size for item in files) + len(value) > MAX_ORDER_EMAIL_TOTAL_ATTACHMENT_BYTES:
                raise ValueError("Допустимо до 10 файлов общим размером до 20 МБ")
            session.add(cls._attachment(actor=actor, row=row, filename=filename, mime_type=mime_type, content=value))
            await session.flush()
            await cls._sync_metadata(session, actor, row)
            cls._changed(row)
            return await cls._result(session, actor, row)
        return await cls._command(session, actor, "attachment.upload", idempotency_key, command, operation)

    @classmethod
    async def get_attachment(cls, session, *, actor, draft_id, attachment_id):
        await cls._get(session, actor, draft_id)
        files = await MailWorkspaceDAO.attachments(session, draft_id, actor.tenant_scope.tenant_id)
        item = next((item for item in files if item.id == attachment_id), None)
        if item is None:
            raise MailNotFoundError("Вложение не найдено")
        return item

    @classmethod
    async def delete_attachment(cls, session, *, actor, draft_id, attachment_id, expected_version, idempotency_key):
        async def operation():
            row = await cls._get(session, actor, draft_id, lock=True)
            cls._require_draft(row, expected_version)
            item = await cls.get_attachment(session, actor=actor, draft_id=draft_id, attachment_id=attachment_id)
            await session.delete(item)
            await session.flush()
            await cls._sync_metadata(session, actor, row)
            cls._changed(row)
            return await cls._result(session, actor, row)
        return await cls._command(session, actor, "attachment.delete", idempotency_key,
            {"draft_id": draft_id, "attachment_id": attachment_id, "expected_version": expected_version}, operation)

    @classmethod
    async def preview(cls, session, *, actor, draft_id):
        return await cls.get_message(session, actor=actor, message_id=draft_id)

    @classmethod
    async def confirm(cls, session, *, actor, draft_id, payload: MailConfirmPayload, idempotency_key):
        if actor.channel != "manager":
            raise PermissionError("Подтвердите актуальное письмо в Manager")
        async def operation():
            row = await cls._get(session, actor, draft_id, lock=True)
            cls._require_draft(row, payload.expected_version)
            from services.mail_workspace_delivery import MailWorkspaceDelivery
            files = await MailWorkspaceDAO.attachments(session, draft_id, actor.tenant_scope.tenant_id)
            await MailWorkspaceDelivery.validate_send(session, actor, row, files)
            if cls._hash(row, files) != payload.content_hash:
                raise MailStateConflictError("Предпросмотр устарел. Проверьте письмо заново")
            row.confirmed_version, row.confirmed_hash = row.version, payload.content_hash
            row.confirmed_by_staff_user_id, row.confirmed_at = actor.staff_user_id, datetime.now()
            return await cls._result(session, actor, row)
        return await cls._command(session, actor, "draft.confirm", idempotency_key,
            {"draft_id": draft_id, **payload.model_dump()}, operation)

    @classmethod
    async def send(cls, session, *, actor, draft_id, payload: MailVersionPayload, idempotency_key,
                   authorize_before_send: Callable[[], Awaitable[None]] | None = None):
        from services.mail_workspace_delivery import MailWorkspaceDelivery
        return await MailWorkspaceDelivery.send(session, actor=actor, draft_id=draft_id,
            payload=payload, idempotency_key=idempotency_key, authorize_before_send=authorize_before_send)

    @classmethod
    async def copy_message(cls, session, *, actor, message_id, payload: MailVersionPayload, idempotency_key):
        async def operation():
            source = await cls._get(session, actor, message_id, lock=True)
            if source.version != payload.expected_version:
                raise MailVersionConflictError(source.version)
            if source.status in {"sending", "unknown", "pending"}:
                raise MailStateConflictError("Сначала проверьте, принято ли исходное письмо почтовым сервером")
            files = await MailWorkspaceDAO.attachments(session, message_id, actor.tenant_scope.tenant_id)
            if source.attachments and not files:
                raise MailStateConflictError("У старого письма не сохранены файлы. Загрузите их в новый черновик вручную")
            account = await MailWorkspaceAccess.require_account(session, actor, source.account_id)
            row = OutgoingEmail(
                tenant_id=actor.tenant_scope.tenant_id, storefront_id=actor.tenant_scope.storefront_id,
                status="draft", account_id=account.id, version=1, from_email=account.email,
                from_name=account.name, recipient_email=source.recipient_email,
                cc_emails=source.cc_emails, bcc_emails=source.bcc_emails,
                subject=source.subject, body_text=source.body_text or cls._html_to_text(source.body_html), body_html=None,
                reply_to=source.reply_to, in_reply_to=source.in_reply_to, references=source.references, order_id=source.order_id, customer_id=source.customer_id,
                retry_of_email_id=(source.retry_of_email_id or int(source.id)) if source.status != "draft" else None,
                created_by_staff_user_id=actor.staff_user_id,
            )
            session.add(row)
            await session.flush()
            for item in files:
                session.add(cls._attachment(actor=actor, row=row, filename=item.filename,
                    mime_type=item.mime_type, content=item.content, metadata=item.source_metadata))
            await session.flush()
            await cls._sync_metadata(session, actor, row)
            return await cls._result(session, actor, row, status_code=201)
        return await cls._command(session, actor, "message.copy", idempotency_key,
            {"message_id": message_id, "expected_version": payload.expected_version}, operation)

    @classmethod
    async def create_legacy_draft(cls, session, *, actor, idempotency_key, to_email, subject,
                                body_text=None, body_html=None, reply_to=None, order_id=None, customer_id=None,
                                attachments: list[MailAttachment] | None = None):
        attachments = attachments or []
        if len(attachments) > 10 or sum(len(item.content) for item in attachments) > MAX_ORDER_EMAIL_TOTAL_ATTACHMENT_BYTES:
            raise ValueError("Допустимо до 10 файлов общим размером до 20 МБ")
        payload = {"to_email": to_email, "subject": subject, "body_text": body_text,
            "body_html": body_html, "reply_to": reply_to, "order_id": order_id, "customer_id": customer_id,
            "attachments": [{"filename": item.filename, "mime_type": item.mime_type,
                "sha256": hashlib.sha256(item.content).hexdigest(), "metadata": item.metadata} for item in attachments]}
        async def operation():
            account = await MailWorkspaceAccess.require_account(session, actor, "system")
            await MailWorkspaceAccess.validate_links(session, actor, order_id=order_id, customer_id=customer_id)
            row = OutgoingEmail(tenant_id=actor.tenant_scope.tenant_id, storefront_id=actor.tenant_scope.storefront_id,
                account_id=account.id, status="draft", recipient_email=to_email, subject=subject,
                body_text=body_text or cls._html_to_text(body_html), body_html=None, reply_to=reply_to, order_id=order_id,
                customer_id=customer_id, from_email=account.email, from_name=account.name,
                created_by_staff_user_id=actor.staff_user_id)
            session.add(row)
            await session.flush()
            for item in attachments:
                session.add(cls._attachment(actor=actor, row=row, filename=item.filename,
                    mime_type=item.mime_type, content=item.content, metadata=item.metadata))
            await session.flush()
            await cls._sync_metadata(session, actor, row)
            return await cls._result(session, actor, row, status_code=201)
        return await cls._command(session, actor, "draft.create_legacy", idempotency_key, payload, operation)

    @staticmethod
    def _html_to_text(value: str | None) -> str:
        if not value:
            return ""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(value, "html.parser")
        for element in soup(["script", "style"]):
            element.decompose()
        return soup.get_text("\n", strip=True)
