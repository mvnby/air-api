"""Eligibility checks shared by native draft creation and open-contract act issuance."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import CustomerContract, Order, OrderDocument, OrderStatus
from models.tenancy import TenantScope
from .errors import ManagedDocumentConflictError


def covers_issue_date(contract: CustomerContract, issue_date: date) -> bool:
    return contract.valid_from.date() <= issue_date <= contract.valid_until.date()


async def validate_act_basis_for_issue(
    session: AsyncSession, *, document: OrderDocument, scope: TenantScope
) -> None:
    if document.doc_type != "act" or document.base_customer_contract_id is None:
        return
    # A retry after render failure completes the already reserved identity.
    if document.official_number:
        return
    row = (await session.execute(
        select(CustomerContract, Order.status)
        .join(Order, Order.customer_id == CustomerContract.customer_id)
        .where(
            Order.id == document.order_id,
            Order.tenant_id == scope.tenant_id,
            Order.storefront_id == scope.storefront_id,
            CustomerContract.id == document.base_customer_contract_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )).one_or_none()
    if row is None or row[1] == OrderStatus.CLOSED:
        raise ManagedDocumentConflictError("Для выпуска нужен открытый заказ клиента этого договора")
    contract = row[0]
    if contract.status != "active" or not covers_issue_date(contract, document.date.date()):
        raise ManagedDocumentConflictError("Открытый договор недоступен на дату акта")
    values = document.render_snapshot.get("values") or {}
    if (values.get("basis.number"), values.get("basis.date")) != (
        contract.number, contract.valid_from.strftime("%d.%m.%Y")
    ):
        raise ManagedDocumentConflictError("Реквизиты договора изменились. Создайте новый черновик акта")
    meta = document.render_snapshot.get("meta") or {}
    if meta.get("document_role_source") != "explicit" and (
        not contract.document_role_type or meta.get("document_role_type") != contract.document_role_type
    ):
        raise ManagedDocumentConflictError(
            "Сверьте названия сторон с открытым договором и создайте черновик с правильными ролями"
        )
