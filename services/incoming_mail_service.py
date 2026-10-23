"""Persist and read the existing IMAP mailbox without creating CRM entities."""

import hashlib
from datetime import datetime
from email.message import Message
from email.utils import getaddresses, parseaddr

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.config import settings
from models.incoming_mail import IncomingMail, IncomingMailAttachment
from models.tenancy import TenantScope
from services.tenant_entity_access_service import TenantEntityAccessService


MAX_INCOMING_BYTES = 30 * 1024 * 1024
MAX_INCOMING_FILES = 20


class IncomingMailService:
    @classmethod
    async def sync(cls, session, *, actor, payload, idempotency_key):
        from schemas_incoming_mail import IncomingMailSyncResponse
        from services.authenticated_command_service import AuthenticatedCommandService
        from services.mail_imap_service import MailImapService
        from services.public_write_idempotency_service import PublicWriteCommandResponse

        await cls._require_access(session, actor)

        async def operation():
            result = await MailImapService.sync_mailbox(
                session, tenant_scope=actor.tenant_scope, limit=payload.limit,
            )
            return PublicWriteCommandResponse(value=IncomingMailSyncResponse(**result), status_code=200,
                resource_type="mailbox", resource_id=actor.tenant_scope.tenant_id, response_max_bytes=2048)

        return await AuthenticatedCommandService.execute(session, actor=actor, command_name="mail.sync",
            idempotency_key=idempotency_key, payload=payload, response_model=IncomingMailSyncResponse,
            operation=operation)

    @staticmethod
    async def _require_access(session: AsyncSession, actor: CommandActor) -> None:
        # Same live account/membership checks as drafts and sends; there is only
        # one configured system mailbox in the current deployment.
        from services.mail_workspace_access import MailWorkspaceAccess

        await MailWorkspaceAccess.require_actor(session, actor)
        if not actor.tenant_scope.is_system:
            raise PermissionError("Почтовый аккаунт недоступен в текущей компании")

    @staticmethod
    async def capture(
        session: AsyncSession, *, tenant_scope: TenantScope, message: Message, raw_email: bytes,
    ) -> IncomingMail | None:
        row, _ = await IncomingMailService.capture_result(session, tenant_scope=tenant_scope, message=message, raw_email=raw_email)
        return row

    @staticmethod
    async def capture_result(
        session: AsyncSession, *, tenant_scope: TenantScope, message: Message, raw_email: bytes,
    ) -> tuple[IncomingMail | None, bool]:
        from services.mail_imap_service import MailImapService

        if not tenant_scope.is_system:
            raise PermissionError("Системная почта недоступна другой компании")
        if len(raw_email) > MAX_INCOMING_BYTES:
            return None, False
        message_id = str(message.get("Message-ID") or "").strip()
        source_key = hashlib.sha256(message_id.encode() + b"\0" + raw_email).hexdigest()
        existing = (await session.execute(select(IncomingMail).where(
            IncomingMail.tenant_id == tenant_scope.tenant_id,
            IncomingMail.account_id == "system", IncomingMail.source_key == source_key,
        ))).scalar_one_or_none()
        if existing:
            return existing, False
        sender_name, sender_email = parseaddr(MailImapService._decode_header_value(message.get("From")))
        text = MailImapService._extract_body(message)
        has_plain = any(part.get_content_type() == "text/plain" and not part.get_filename()
                        for part in message.walk())
        body_html = None if has_plain else text
        from services.mail_headers import message_ids, reply_addresses
        parent = message_ids(str(message.get("In-Reply-To") or ""))
        row = IncomingMail(
            tenant_id=tenant_scope.tenant_id, account_id="system", source_key=source_key,
            reply_to=reply_addresses(str(message.get("Reply-To") or "")),
            in_reply_to=parent[-1] if parent else None, references=message_ids(str(message.get("References") or "")),
            message_id=(message_ids(message_id) or [None])[0], sender_email=sender_email.lower().replace("\x00", ""), sender_name=sender_name.replace("\x00", ""),
            recipient_email=", ".join(address.replace("\x00", "") for _, address in getaddresses(message.get_all("To", []))),
            cc_emails=[address.replace("\x00", "") for _, address in getaddresses(message.get_all("Cc", []))],
            subject=MailImapService._decode_header_value(message.get("Subject")),
            body_text=MailImapService._strip_html(text) if body_html else text,
            body_html=body_html,
            received_at=MailImapService._parse_email_date(message.get("Date")) or datetime.now(),
        )
        # A duplicate concurrent import must not roll back unrelated intake work.
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
                metadata = []
                for position, attachment in enumerate(MailImapService._extract_original_attachments(message)):
                    filename = attachment.filename.replace("\r", "").replace("\n", "").replace("\x00", "")[:255] or "attachment"
                    file = IncomingMailAttachment(
                        email_id=row.id, tenant_id=row.tenant_id, filename=filename,
                        mime_type=attachment.content_type, size=len(attachment.content),
                        sha256=hashlib.sha256(attachment.content).hexdigest(), content=attachment.content,
                    )
                    # Retain honest metadata for files beyond the bounded storage
                    # allowance; they cannot silently disappear on reply/copy.
                    if position < MAX_INCOMING_FILES:
                        session.add(file)
                        await session.flush()
                    metadata.append({"id": file.id, "filename": filename,
                                     "mime_type": file.mime_type, "size": file.size,
                                     "sha256": file.sha256, "available": file.id is not None})
                row.attachments = metadata
                session.add(row)
                await session.flush()
        except IntegrityError:
            row = (await session.execute(select(IncomingMail).where(
                IncomingMail.tenant_id == tenant_scope.tenant_id,
                IncomingMail.account_id == "system", IncomingMail.source_key == source_key,
            ))).scalar_one()
            return row, False
        return row, True

    @classmethod
    async def _projection(cls, session: AsyncSession, actor: CommandActor, row: IncomingMail):
        from schemas_mail import MailMessageResponse

        order_id, customer_id = row.order_id, row.customer_id
        if order_id and not await TenantEntityAccessService.get_order(session, order_id, tenant_scope=actor.tenant_scope):
            order_id = None
        if customer_id and not await TenantEntityAccessService.get_customer(session, customer_id, tenant_scope=actor.tenant_scope):
            customer_id = None
        attachments = [dict(item, download_url=(
            f"/api/manager/mail/messages/{-row.id}/attachments/{item['id']}" if item.get("available") else None
        )) for item in row.attachments]
        return MailMessageResponse(
            id=-row.id, version=1, status="received", folder="inbox", account_id=row.account_id,
            sender_email=row.sender_email, sender_name=row.sender_name,
            reply_to=row.reply_to, message_id=row.message_id, in_reply_to=row.in_reply_to, references=row.references,
            to=[address.strip() for address in row.recipient_email.split(",") if address.strip()],
            cc=row.cc_emails, bcc=[], subject=row.subject, body_text=row.body_text,
            attachments=attachments, order_id=order_id, customer_id=customer_id,
            created_at=row.received_at, updated_at=row.created_at,
            manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/mail?message={-row.id}",
        )

    @classmethod
    async def list_messages(cls, session: AsyncSession, *, actor: CommandActor,
                            page: int = 1, limit: int = 50, q: str | None = None,
                            order_id: int | None = None, customer_id: int | None = None,
                            status: str | None = None):
        await cls._require_access(session, actor)
        filters = [IncomingMail.tenant_id == actor.tenant_scope.tenant_id,
                   IncomingMail.account_id == "system"]
        if q:
            query = f"%{q.strip()}%"
            filters.append(or_(IncomingMail.subject.ilike(query), IncomingMail.sender_email.ilike(query),
                               IncomingMail.body_text.ilike(query)))
        if order_id is not None:
            if not await TenantEntityAccessService.get_order(session, order_id, tenant_scope=actor.tenant_scope):
                raise LookupError("Заказ недоступен")
            filters.append(IncomingMail.order_id == order_id)
        if customer_id is not None:
            if not await TenantEntityAccessService.get_customer(session, customer_id, tenant_scope=actor.tenant_scope):
                raise LookupError("Клиент недоступен")
            filters.append(IncomingMail.customer_id == customer_id)
        if status and status != "received":
            return [], 0
        total = (await session.execute(select(func.count()).select_from(IncomingMail).where(*filters))).scalar_one()
        rows = (await session.execute(select(IncomingMail).where(*filters).order_by(
            IncomingMail.received_at.desc(), IncomingMail.id.desc(),
        ).offset((page - 1) * limit).limit(min(limit, 100)))).scalars().all()
        items = [await cls._projection(session, actor, row) for row in rows]
        return [item.model_copy(update={"body_text": item.body_text[:300]}) for item in items], int(total)

    @classmethod
    async def get_message(cls, session: AsyncSession, *, actor: CommandActor, email_id: int):
        await cls._require_access(session, actor)
        row = (await session.execute(select(IncomingMail).where(
            IncomingMail.id == -int(email_id), IncomingMail.tenant_id == actor.tenant_scope.tenant_id,
            IncomingMail.account_id == "system",
        ))).scalar_one_or_none()
        if row is None:
            raise LookupError("Письмо не найдено")
        return await cls._projection(session, actor, row)

    @classmethod
    async def read_attachment(cls, session: AsyncSession, *, actor: CommandActor, email_id: int, attachment_id: int):
        await cls.get_message(session, actor=actor, email_id=email_id)
        file = (await session.execute(select(IncomingMailAttachment).where(
            IncomingMailAttachment.id == attachment_id, IncomingMailAttachment.email_id == -email_id,
            IncomingMailAttachment.tenant_id == actor.tenant_scope.tenant_id,
        ))).scalar_one_or_none()
        if not file:
            raise LookupError("Вложение не найдено")
        if len(file.content) != file.size or hashlib.sha256(file.content).hexdigest() != file.sha256:
            raise RuntimeError("Сохранённое вложение повреждено")
        return file
