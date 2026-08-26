from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Order, OrderDocument
from models.tenancy import TenantScope
from modules.documents.domain import DocumentStatus

from .errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError


ACTIVE_REPLACEMENT_STATUSES = (
    DocumentStatus.DRAFT.value,
    DocumentStatus.ISSUED.value,
    DocumentStatus.SENT.value,
    DocumentStatus.SIGNED.value,
)


async def lock_replacement_target(
    session: AsyncSession,
    *,
    tenant_scope: TenantScope,
    order_id: int,
    document_type: str,
    target_document_id: int,
    replacement_document_id: int | None = None,
) -> OrderDocument:
    target = (
        await session.execute(
            select(OrderDocument)
            .join(Order, Order.id == OrderDocument.order_id)
            .where(
                OrderDocument.id == target_document_id,
                OrderDocument.tenant_id == tenant_scope.tenant_id,
                Order.tenant_id == tenant_scope.tenant_id,
                Order.storefront_id == tenant_scope.storefront_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if target is None or target.order_id != order_id:
        raise ManagedDocumentNotFoundError("Заменяемый документ не найден")
    if target.status not in {
        DocumentStatus.ISSUED.value,
        DocumentStatus.SENT.value,
        DocumentStatus.SIGNED.value,
    }:
        raise ManagedDocumentConflictError(
            "Заменить можно только действующий выпущенный документ"
        )
    if target.doc_type != document_type:
        raise ManagedDocumentConflictError("Документ-замена должен иметь тот же тип")
    duplicate_query = select(OrderDocument.id).where(
        OrderDocument.tenant_id == tenant_scope.tenant_id,
        OrderDocument.replaces_document_id == target_document_id,
        OrderDocument.status.in_(ACTIVE_REPLACEMENT_STATUSES),
    )
    if replacement_document_id is not None:
        duplicate_query = duplicate_query.where(
            OrderDocument.id != replacement_document_id
        )
    duplicate = (await session.execute(duplicate_query.limit(1))).scalar_one_or_none()
    if duplicate is not None:
        raise ManagedDocumentConflictError(
            "Для документа уже готовится или выпущена замена"
        )
    return target
