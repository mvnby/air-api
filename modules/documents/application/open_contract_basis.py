"""Native basis resolution shared by explicit, automatic and saved document selections."""

from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import CustomerContract, DocumentLegalEntity, Order, OrderDocument, OrderStatus
from models.tenancy import TenantScope

from .errors import ManagedDocumentConflictError


async def _contract_problem(
    session: AsyncSession, contract: CustomerContract | None, *, order: Order, issuer_id: int, issue_date: date,
) -> str | None:
    if contract is None or contract.customer_id != order.customer_id:
        return "Договор клиента не найден"
    if contract.status != "active":
        return "Открытый договор недоступен для новых документов"
    if not contract.valid_from.date() <= issue_date <= contract.valid_until.date():
        return "Дата документа выходит за срок открытого договора"
    if contract.legal_entity_id is not None:
        if contract.legal_entity_id != issuer_id:
            return "Договор относится к другому юридическому лицу"
    elif await session.scalar(select(DocumentLegalEntity.id).where(
        DocumentLegalEntity.tenant_id == order.tenant_id, DocumentLegalEntity.status == "active",
        DocumentLegalEntity.id != issuer_id,
    ).limit(1)):
        return "Сверьте и укажите наше юридическое лицо в открытом договоре клиента"
    return None


def _order_bases(order: Order):
    return select(OrderDocument, CustomerContract).outerjoin(
        CustomerContract, CustomerContract.source_document_id == OrderDocument.id,
    ).where(
        OrderDocument.order_id == order.id,
        or_(OrderDocument.tenant_id == order.tenant_id, OrderDocument.tenant_id.is_(None)),
        OrderDocument.doc_type.in_(("contract", "invoice", "offer")),
        or_(OrderDocument.status.in_(("issued", "sent", "signed")), OrderDocument.status.is_(None)),
    )


async def resolve_native_basis(
    session: AsyncSession, *, order: Order, issuer_id: int, document_type: str, issue_date: date,
    base_document_id: int | None, base_customer_contract_id: int | None,
    lock: bool = False,
) -> tuple[OrderDocument | None, CustomerContract | None]:
    if document_type not in {"act", "tn2", "ttn1", "invoice"}:
        return None, None
    if not base_document_id:
        contract_id = base_customer_contract_id or order.customer_contract_id
        if contract_id:
            statement = select(CustomerContract).where(CustomerContract.id == contract_id)
            if lock:
                statement = statement.with_for_update().execution_options(populate_existing=True)
            contract = await session.scalar(statement)
            problem = await _contract_problem(
                session, contract, order=order, issuer_id=issuer_id, issue_date=issue_date,
            )
            if problem is None:
                return None, contract
            if base_customer_contract_id or document_type != "invoice":
                raise ManagedDocumentConflictError(problem)

    # A framework source document and its client register entry are one basis.
    # Load both together, including when selecting automatically on the source order.
    documents = _order_bases(order)
    if base_document_id:
        documents = documents.where(OrderDocument.id == base_document_id)
    else:
        documents = documents.where(
            or_(OrderDocument.legal_entity_id.is_(None), OrderDocument.legal_entity_id == issuer_id),
            or_(OrderDocument.doc_type != "invoice", OrderDocument.business_role == "offer"),
        ).order_by((OrderDocument.doc_type == "contract").desc(), OrderDocument.created_at.desc(), OrderDocument.id.desc())
    if lock:
        documents = documents.with_for_update(of=OrderDocument).execution_options(populate_existing=True)
    for document, entry in (await session.execute(documents)).all():
        if document.legal_entity_id is not None and document.legal_entity_id != issuer_id:
            raise ManagedDocumentConflictError("Документ-основание относится к другому юридическому лицу")
        if document.doc_type == "invoice" and document.business_role != "offer":
            raise ManagedDocumentConflictError("Обычный счет на оплату не является основанием акта")
        if entry is None:
            return document, None
        if lock:
            entry = await session.scalar(select(CustomerContract).where(CustomerContract.id == entry.id)
                                         .with_for_update().execution_options(populate_existing=True))
        problem = await _contract_problem(session, entry, order=order, issuer_id=issuer_id, issue_date=issue_date)
        if problem is None:
            return None, entry
        if base_document_id:
            raise ManagedDocumentConflictError(problem)
    if base_document_id:
        raise ManagedDocumentConflictError("Документ-основание не найден в заказе")
    return None, None

async def validate_saved_basis_for_issue(
    session: AsyncSession, *, document: OrderDocument, scope: TenantScope,
) -> None:
    # Rendering retries complete a previously validated reservation with its frozen facts.
    if document.official_number or not (document.base_document_id or document.base_customer_contract_id):
        return
    order = await session.scalar(select(Order).where(
        Order.id == document.order_id, Order.tenant_id == scope.tenant_id,
        Order.storefront_id == scope.storefront_id,
    ).with_for_update().execution_options(populate_existing=True))
    if order is None or order.status == OrderStatus.CLOSED:
        raise ManagedDocumentConflictError("Для выпуска нужен открытый заказ клиента этого договора")
    active_issuer = await session.scalar(select(DocumentLegalEntity.id).where(
        DocumentLegalEntity.id == document.legal_entity_id, DocumentLegalEntity.tenant_id == scope.tenant_id,
        DocumentLegalEntity.status == "active",
    ).with_for_update(read=True))
    if active_issuer is None:
        raise ManagedDocumentConflictError("Юридическое лицо документа больше не активно")
    _, entry = await resolve_native_basis(
        session, order=order, document_type=document.doc_type, issuer_id=document.legal_entity_id,
        issue_date=document.date.date(), base_document_id=document.base_document_id,
        base_customer_contract_id=document.base_customer_contract_id, lock=True,
    )
    if entry is None:
        return
    values = document.render_snapshot.get("values") or {}
    if (values.get("basis.number"), values.get("basis.date")) != (
        entry.number, entry.valid_from.strftime("%d.%m.%Y"),
    ):
        raise ManagedDocumentConflictError("Реквизиты договора изменились. Создайте новый черновик документа")
    meta = document.render_snapshot.get("meta") or {}
    if document.doc_type == "act" and meta.get("document_role_source") != "explicit" and (
        not entry.document_role_type or meta.get("document_role_type") != entry.document_role_type
    ):
        raise ManagedDocumentConflictError(
            "Сверьте названия сторон с открытым договором и создайте черновик с правильными ролями"
        )
    if document.base_document_id is not None:
        # Older drafts may have selected the source as a one-time order document.
        # Both printed facts have just been checked, so canonicalizing the link
        # doesn't change their editable contents or the immutable party snapshot.
        document.base_document_id = None
        document.base_customer_contract_id = entry.id
        document.render_snapshot = {
            **document.render_snapshot,
            "meta": {**meta, "base_document_id": None, "base_customer_contract_id": entry.id},
        }
