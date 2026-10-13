"""Order documents use the standalone draft/transport and existing lifecycle."""

from core.command_actor import CommandActor
from crud.mail_workspace import MailWorkspaceDAO
from services.mail_smtp_service import MailAttachment, MailSmtpService
from services.tenant_entity_access_service import TenantEntityAccessService


class OrderMailDeliveryService:
    @classmethod
    async def create_draft(cls, session, *, actor: CommandActor, order_id: int, payload, idempotency_key):
        from services.mail_workspace_service import MailWorkspaceService
        from schemas_mail import MailMessageResponse
        from services.authenticated_command_service import AuthenticatedCommandService
        from services.mail_workspace_access import MailWorkspaceAccess
        from services.public_write_idempotency_service import PublicWriteCommandResponse

        # The replay fence precedes document retrieval: retrying a lost create
        # response returns its first snapshots even when a source PDF changed.
        await MailWorkspaceAccess.require_actor(session, actor, write=True)
        await MailWorkspaceAccess.validate_links(session, actor, order_id=order_id, customer_id=None)

        async def operation():
            order, attachments = await MailSmtpService.prepare_order_attachments(
                session, tenant_scope=actor.tenant_scope, order_id=order_id,
                document_ids=payload.document_ids, registration_certificate_id=payload.registration_certificate_id,
                legal_entity_id=payload.legal_entity_id,
            )
            outcome = await MailWorkspaceService.create_legacy_draft(
                session, actor=actor, idempotency_key=idempotency_key, to_email=payload.to_email,
                subject=payload.subject, body_text=payload.body_text, body_html=payload.body_html,
                reply_to=payload.reply_to, order_id=order_id, customer_id=order.customer_id, attachments=attachments,
            )
            return PublicWriteCommandResponse(value=outcome.value, status_code=201,
                resource_type="outgoing_email", resource_id=outcome.value.id,
                response_max_bytes=MailWorkspaceService.RESPONSE_MAX_BYTES)

        return await AuthenticatedCommandService.execute(
            session, actor=actor, command_name="mail.order_draft.create", idempotency_key=idempotency_key,
            payload={"order_id": order_id, **payload.model_dump()}, response_model=MailMessageResponse,
            operation=operation,
        )

    @staticmethod
    async def validate_sources(session, *, actor: CommandActor, email, files):
        """Private bytes are frozen; access to the source objects must still exist."""
        for file in files:
            metadata = file.source_metadata or {}
            if metadata.get("document_id"):
                document = await TenantEntityAccessService.get_order_document(
                    session, int(metadata["document_id"]), tenant_scope=actor.tenant_scope,
                )
                if document is None or document.order_id != email.order_id:
                    raise PermissionError("Документ во вложении недоступен")
                await session.refresh(document)
                if metadata.get("native") and document.status not in {"issued", "sent", "signed"}:
                    raise ValueError("Документ во вложении больше не доступен для отправки")
            if metadata.get("registration_certificate_id"):
                from models import LegalEntityAttachment

                certificate = await session.get(LegalEntityAttachment, metadata["registration_certificate_id"])
                if certificate is None or certificate.tenant_id != actor.tenant_scope.tenant_id:
                    raise PermissionError("Реквизиты во вложении недоступны")

    @classmethod
    async def after_sent(cls, session, *, actor: CommandActor, email):
        if email.status != "sent" or email.order_id is None:
            return
        from services.mail_workspace_access import MailWorkspaceAccess

        await MailWorkspaceAccess.require_actor(session, actor)
        order = await TenantEntityAccessService.get_order(
            session, email.order_id, tenant_scope=actor.tenant_scope,
        )
        if order is None:
            return
        files = await MailWorkspaceDAO.attachments(session, int(email.id), actor.tenant_scope.tenant_id)
        attachments = []
        for file in files:
            metadata = dict(file.source_metadata or {})
            if metadata.get("document_id"):
                document = await TenantEntityAccessService.get_order_document(
                    session, int(metadata["document_id"]), tenant_scope=actor.tenant_scope,
                )
                if document is not None:
                    await session.refresh(document)
                # Sending a frozen older edition must not mark a newer edition sent.
                if document is None or document.snapshot_version != metadata.get("snapshot_version"):
                    continue
            attachments.append(MailAttachment(filename=file.filename, content=file.content,
                                               mime_type=file.mime_type, metadata=metadata))
        await MailSmtpService.apply_order_delivery(session, tenant_scope=actor.tenant_scope,
                                                   order=order, attachments=attachments, email_row=email)
