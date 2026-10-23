"""Durable send claim before SMTP, conservative results after external effects."""

import asyncio
import logging
import re
import smtplib
import uuid
from datetime import datetime, timedelta
from email.utils import formataddr

from sqlalchemy.orm import SessionTransactionOrigin
from sqlalchemy.ext.asyncio import AsyncConnection

from crud.mail_workspace import MailWorkspaceDAO
from schemas_mail import MailMessageResponse
from services.authenticated_command_service import AuthenticatedCommandService
from services.mail_smtp_service import MailAttachment, MailSmtpService
from services.mail_workspace_access import MailStateConflictError, MailVersionConflictError, MailWorkspaceAccess
from services.public_write_idempotency_service import PublicWriteCommandOutcome

logger = logging.getLogger(__name__)
ADDRESS = re.compile(r"^[^\s<>@,;\r\n]+@[^\s<>@,;\r\n]+\.[^\s<>@,;\r\n]+$")


class MailWorkspaceDelivery:
    CLAIM_RECOVERY_AFTER = timedelta(minutes=10)

    @staticmethod
    async def validate_send(session, actor, row, files):
        await MailWorkspaceAccess.require_actor(session, actor, write=True)
        account = await MailWorkspaceAccess.require_account(session, actor, row.account_id)
        if row.from_email != account.email or row.from_name != account.name:
            raise MailStateConflictError("Настройки отправителя изменились. Сохраните и проверьте черновик заново")
        addresses = [value.strip() for value in row.recipient_email.split(",") if value.strip()]
        addresses += row.cc_emails or []
        addresses += row.bcc_emails or []
        if not addresses or len(addresses) > 50 or any(not ADDRESS.fullmatch(value) or len(value) > 254 for value in addresses):
            raise ValueError("Укажите корректные адреса получателей (не больше 50)")
        from services.mail_headers import valid_message_id
        if (row.in_reply_to and not valid_message_id(row.in_reply_to)) or len(row.references or []) > 50 or any(not valid_message_id(value) for value in row.references or []):
            raise ValueError("Некорректные заголовки цепочки писем")
        if not row.subject.strip() or any(char in row.subject for char in "\r\n"):
            raise ValueError("Укажите тему письма без переноса строки")
        if not (row.body_text or "").strip() and not (row.body_html or "").strip():
            raise ValueError("Введите текст письма")
        if row.body_html:
            raise MailStateConflictError("Сохраните письмо как обычный текст, чтобы весь отправляемый текст был виден в предпросмотре")
        if row.attachments and len(files) != len(row.attachments):
            raise MailStateConflictError("У письма не сохранены все файлы. Загрузите вложения в новый черновик")
        # Detect corrupted stored bytes before contact with the mail server.
        import hashlib
        if any(len(item.content) != item.size or hashlib.sha256(item.content).hexdigest() != item.sha256 for item in files):
            raise MailStateConflictError("Не удалось проверить сохранённые вложения")
        from services.order_mail_delivery_service import OrderMailDeliveryService
        await OrderMailDeliveryService.validate_sources(session, actor=actor, email=row, files=files)

    @classmethod
    async def recover_stale_claim(cls, session, row, *, actor=None):
        if row.status != "sending" or row.send_started_at is None:
            return False
        started = row.send_started_at.replace(tzinfo=None)
        if datetime.now() - started < cls.CLAIM_RECOVERY_AFTER:
            return False
        if actor is None:
            return False
        locked = await MailWorkspaceDAO.get(session, int(row.id), actor.tenant_scope, lock=True)
        if locked is None or locked.status != "sending":
            return False
        locked.status = "unknown"
        locked.error = "Процесс отправки прервался. Перед повторным письмом проверьте папку отправленных и журнал почтового сервера"
        locked.updated_at = datetime.now()
        from models.command_audit import CommandAuditEvent
        session.add(CommandAuditEvent(tenant_id=actor.tenant_scope.tenant_id,
            storefront_id=actor.tenant_scope.storefront_id, staff_user_id=actor.staff_user_id,
            channel=actor.channel, operation="mail.delivery.recover", request_id=locked.send_token or "recovery",
            resource_type="outgoing_email", resource_id=int(locked.id), result="unknown"))
        return True

    @staticmethod
    def _build(row, files):
        message = MailSmtpService.build_message(
            to_email=row.recipient_email, subject=row.subject, body_text=row.body_text,
            body_html=row.body_html, reply_to=row.reply_to,
            attachments=[MailAttachment(filename=item.filename, mime_type=item.mime_type, content=item.content) for item in files],
        )
        # Send only the immutable saved sender, even if config changes after claiming.
        message.replace_header("From", formataddr((row.from_name or "", row.from_email)))
        message["Message-ID"] = f"<kitlane-{row.id}-{row.send_token}@{row.from_email.split('@')[-1]}>"
        if row.in_reply_to:
            message["In-Reply-To"] = row.in_reply_to
        if row.references:
            message["References"] = " ".join(row.references)
        if row.cc_emails:
            message["Cc"] = ", ".join(row.cc_emails)
        if row.bcc_emails:
            message["Bcc"] = ", ".join(row.bcc_emails)
        return message

    @staticmethod
    def _known_rejection(exc):
        # These protocol replies prove that SMTP did not accept the message.
        return isinstance(exc, (
            smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused,
            smtplib.SMTPSenderRefused, smtplib.SMTPDataError, smtplib.SMTPConnectError,
            PermissionError,
        ))

    @classmethod
    async def send(cls, session, *, actor, draft_id, payload, idempotency_key, authorize_before_send=None):
        from services.mail_workspace_service import MailWorkspaceService as Workspace
        transaction = session.get_transaction()
        if (isinstance(session.bind, AsyncConnection) and session.bind.in_transaction()) or session.info.get("mvn_command_transaction_depth") or (
            transaction is not None and transaction.sync_transaction.origin is not SessionTransactionOrigin.AUTOBEGIN
        ):
            raise ValueError("Отправка требует собственной завершённой транзакции")
        send_token = uuid.uuid4().hex

        async def claim():
            row = await Workspace._get(session, actor, draft_id, lock=True)
            if row.version != payload.expected_version:
                raise MailVersionConflictError(row.version)
            if row.status != "draft":
                # The row itself is the fence across actors, keys and retries.
                await cls.recover_stale_claim(session, row, actor=actor)
                return await Workspace._result(session, actor, row)
            files = await MailWorkspaceDAO.attachments(session, draft_id, actor.tenant_scope.tenant_id)
            await cls.validate_send(session, actor, row, files)
            if row.confirmed_version != row.version or row.confirmed_hash != Workspace._hash(row, files) or row.confirmed_by_staff_user_id != actor.staff_user_id:
                raise MailStateConflictError("Проверьте и явно подтвердите актуальную версию письма в Manager")
            # Construct while still in the transaction: malformed headers cannot leave a live claim.
            row.send_token = send_token
            cls._build(row, files)
            row.status, row.error = "sending", None
            row.send_started_at, row.sent_by_staff_user_id = datetime.now(), actor.staff_user_id
            row.updated_at = datetime.now()
            return await Workspace._result(session, actor, row)

        outcome = await Workspace._command(session, actor, "draft.send", idempotency_key,
            {"draft_id": draft_id, "expected_version": payload.expected_version}, claim)
        # Receipt replay must expose current delivery state, without another transport call.
        if outcome.replayed or outcome.value.status != "sending":
            current = await Workspace.get_message(session, actor=actor, message_id=draft_id)
            return PublicWriteCommandOutcome(value=current, status_code=200, replayed=outcome.replayed)
        row = await MailWorkspaceDAO.get(session, draft_id, actor.tenant_scope)
        if row.send_token != send_token:
            return PublicWriteCommandOutcome(value=await Workspace._project(session, row, actor), status_code=200, replayed=False)
        result, error = "sent", None
        smtp_started = False
        authorization_error = None
        try:
            files = await MailWorkspaceDAO.attachments(session, draft_id, actor.tenant_scope.tenant_id)
            message = cls._build(row, files)
            # Live authorization is rechecked after the durable claim and immediately before SMTP.
            await cls.validate_send(session, actor, row, files)
            await MailWorkspaceAccess.validate_links(session, actor, order_id=row.order_id, customer_id=row.customer_id)
            if authorize_before_send is not None:
                try:
                    await authorize_before_send()
                except Exception as exc:
                    authorization_error = exc
                    raise
            await session.commit()
            if session.in_transaction():
                raise RuntimeError("SMTP claim has not been committed")
            smtp_started = True
            await asyncio.to_thread(MailSmtpService.send_message, message)
        except Exception as exc:
            result = "failed" if not smtp_started or cls._known_rejection(exc) else "unknown"
            # SMTP exceptions can contain private data/credentials; return a bounded fixed message.
            error = ("Письмо не отправлено: проверьте актуальные права доступа и настройки"
                if not smtp_started else
                "Почтовый сервер отклонил письмо. Можно создать новый черновик с теми же файлами"
                if result == "failed" else
                "Результат отправки неизвестен. Проверьте папку отправленных и журнал почтового сервера; повтор может создать дубликат")
            logger.warning("MAIL_WORKSPACE_TRANSPORT email=%s result=%s exception=%s", draft_id, result, type(exc).__name__)
        async def finish():
            # Finalize even if access was revoked during SMTP; no second send is authorized.
            row = await MailWorkspaceDAO.get(session, draft_id, actor.tenant_scope, lock=True)
            if row is not None and row.status == "sending" and row.send_token == send_token:
                row.status, row.error, row.updated_at = result, error, datetime.now()
                if result == "sent":
                    row.sent_at = datetime.now()
                    row.delivery_projection_pending = row.order_id is not None
                await session.flush()
            return await Workspace._result(session, actor, row)
        await AuthenticatedCommandService.execute(
            session, actor=actor, command_name="mail.delivery.finish", idempotency_key=f"mail-result-{send_token}",
            payload={"draft_id": draft_id, "send_token": send_token, "status": result},
            response_model=MailMessageResponse, operation=finish,
        )
        await MailWorkspaceAccess.require_actor(session, actor)
        if authorization_error is not None:
            raise authorization_error
        current = await Workspace.get_message(session, actor=actor, message_id=draft_id)
        return PublicWriteCommandOutcome(value=current, status_code=200, replayed=False)

    @classmethod
    async def recover_projection(cls, session, *, actor, email_id):
        """Complete a committed mail obligation; retries never call the transport.

        Another currently authorized company member may finish it after the
        sender leaves. Revocation leaves the obligation pending for that member.
        The row lock serializes different actors/keys; clearing pending and the
        lifecycle writes share the command transaction.
        """
        from services.order_mail_delivery_service import OrderMailDeliveryService
        from services.command_transaction import command_transaction
        try:
            async with command_transaction(session):
                await MailWorkspaceAccess.require_actor(session, actor, write=True)
                row = await MailWorkspaceDAO.get(session, email_id, actor.tenant_scope, lock=True)
                if row is None or row.status != "sent" or not row.delivery_projection_pending:
                    return
                await MailWorkspaceAccess.validate_links(session, actor, order_id=row.order_id, customer_id=row.customer_id)
                await OrderMailDeliveryService.after_sent(session, actor=actor, email=row, commit=False)
                row.delivery_projection_pending = False
                from models.command_audit import CommandAuditEvent
                session.add(CommandAuditEvent(tenant_id=actor.tenant_scope.tenant_id,
                    storefront_id=actor.tenant_scope.storefront_id, staff_user_id=actor.staff_user_id,
                    channel=actor.channel, operation="mail.delivery.project", request_id=row.send_token or str(row.id),
                    resource_type="outgoing_email", resource_id=row.id, result="completed"))
                await session.flush()
        except Exception as exc:
            # The saved SMTP result remains durable; the failed projection and
            # pending flag rollback together. A later authorized read retries it.
            logger.warning("MAIL_ORDER_DELIVERY_PROJECTION_PENDING email=%s exception=%s", email_id, type(exc).__name__)
