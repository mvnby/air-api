from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import OrderDocument
from models.tenancy import TenantScope
from modules.documents.domain import (
    DocumentLifecycleState,
    DocumentStatus,
    transition_document,
)
from services.tenant_entity_access_service import TenantEntityAccessService

from .errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError


class ManagedDocumentDeliveryService:
    """Record delivery outcomes without coupling mail transport to rendering."""

    @classmethod
    async def mark_sent(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document_ids: list[int],
        sent_at: datetime,
    ) -> list[OrderDocument]:
        normalized_ids = list(dict.fromkeys(int(value) for value in document_ids))
        documents: list[OrderDocument] = []
        for document_id in normalized_ids:
            document = await TenantEntityAccessService.get_order_document(
                session,
                document_id,
                tenant_scope=tenant_scope,
                for_update=True,
            )
            if document is None:
                raise ManagedDocumentNotFoundError("Документ не найден")
            if document.status == DocumentStatus.ISSUED.value:
                cls._apply_lifecycle(
                    document,
                    transition_document(
                        cls._lifecycle_state(document),
                        DocumentStatus.SENT,
                        at=sent_at,
                    ),
                )
                session.add(document)
            elif document.status not in {
                DocumentStatus.SENT.value,
                DocumentStatus.SIGNED.value,
            }:
                raise ManagedDocumentConflictError(
                    "Отправить можно только выпущенный документ"
                )
            documents.append(document)

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ManagedDocumentConflictError(
                "Не удалось сохранить отправку документов"
            ) from exc
        for document in documents:
            await session.refresh(document)
        return documents

    @staticmethod
    def _lifecycle_state(document: OrderDocument) -> DocumentLifecycleState:
        try:
            status = DocumentStatus(str(document.status))
        except ValueError as exc:
            raise ManagedDocumentConflictError(
                "Документ не относится к управляемому жизненному циклу"
            ) from exc
        return DocumentLifecycleState(
            status=status,
            issued_at=document.issued_at,
            sent_at=document.sent_at,
            signed_at=document.signed_at,
            voided_at=document.voided_at,
            void_reason=document.void_reason,
        )

    @staticmethod
    def _apply_lifecycle(
        document: OrderDocument, state: DocumentLifecycleState
    ) -> None:
        document.status = state.status.value
        document.issued_at = state.issued_at
        document.sent_at = state.sent_at
        document.signed_at = state.signed_at
        document.voided_at = state.voided_at
        document.void_reason = state.void_reason
