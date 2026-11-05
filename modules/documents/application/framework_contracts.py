"""Register issued native framework contracts in the reusable customer register."""

from datetime import date, datetime

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Customer, CustomerContract, DocumentLegalEntity, Order, OrderDocument, OrderStatus, Tenant
from models.tenancy import TenantScope
from modules.documents.domain.roles import ROLE_FORMS
from services.customer_party import is_business_customer_type

from .errors import ManagedDocumentConflictError


def is_framework(document: OrderDocument) -> bool:
    values = (document.render_snapshot or {}).get("values") or {}
    return document.doc_type == "contract" and values.get("contract.scenario") == "framework"


async def _matches_historical_customer(session, customer, values) -> bool:
    """Old drafts did not freeze a customer ID. Require one unambiguous business identity."""
    unp = str(values.get("customer.unp") or "").strip()
    full_name = str(values.get("customer.full_name") or "").strip()
    if (not unp or not full_name or unp != (customer.inn or "").strip()
            or full_name != (customer.full_legal_name or customer.name).strip()):
        return False
    matches = await session.scalars(
        select(Customer.id).where(Customer.tenant_id == customer.tenant_id, func.trim(Customer.inn) == unp).limit(2)
    )
    return list(matches) == [customer.id]


def _contract_facts(document):
    snapshot = document.render_snapshot
    values = snapshot["values"]
    role = (snapshot.get("meta") or {}).get("document_role_type") or values.get("document.role_type")
    if role not in ROLE_FORMS:
        raise ManagedDocumentConflictError("Сверьте названия сторон и создайте новый черновик рамочного договора")
    try:
        valid_until = datetime.strptime(values.get("contract.valid_until") or "", "%d.%m.%Y")
    except (ValueError, TypeError) as exc:
        raise ManagedDocumentConflictError("Укажите срок действия рамочного договора") from exc
    if valid_until.date() < document.date.date():
        raise ManagedDocumentConflictError("Срок рамочного договора заканчивается до даты выпуска")
    return role, valid_until


async def prepare_framework_registration(session: AsyncSession, document: OrderDocument, scope: TenantScope):
    """Validate before reserving a number; pin an unambiguously recovered legacy draft in that same commit."""
    if not is_framework(document):
        return
    _contract_facts(document)
    snapshot = document.render_snapshot
    meta = snapshot.get("meta") or {}
    frozen_customer_id = meta.get("customer_id")
    if document.official_number and frozen_customer_id:
        # The first issuance attempt already pinned the party. A retry after a
        # renderer error completes the same document, even if the order was edited.
        return
    row = (await session.execute(
        select(Customer, Order.status, DocumentLegalEntity.status)
        .join(Order, Order.customer_id == Customer.id)
        .join(DocumentLegalEntity, DocumentLegalEntity.tenant_id == Order.tenant_id)
        .where(
            Order.id == document.order_id, Order.tenant_id == scope.tenant_id,
            Order.storefront_id == scope.storefront_id, Customer.tenant_id == scope.tenant_id,
            DocumentLegalEntity.id == document.legal_entity_id,
        ).with_for_update().execution_options(populate_existing=True)
    )).one_or_none()
    if row is None:
        raise ManagedDocumentConflictError("Сверьте клиента и наше юридическое лицо рамочного договора")
    customer, order_status, issuer_status = row
    if order_status == OrderStatus.CLOSED or issuer_status != "active":
        raise ManagedDocumentConflictError("Для выпуска нужны открытый заказ и активное юридическое лицо")
    if not is_business_customer_type(customer.type):
        raise ManagedDocumentConflictError("Для рамочного договора выберите организацию или ИП")
    if frozen_customer_id is None and await _matches_historical_customer(session, customer, snapshot["values"]):
        document.render_snapshot = {**snapshot, "meta": {**meta, "customer_id": customer.id}}
        frozen_customer_id = customer.id
    if frozen_customer_id != customer.id:
        raise ManagedDocumentConflictError("Сверьте клиента заказа и создайте новый черновик рамочного договора")


async def register_issued_framework(session: AsyncSession, document: OrderDocument, scope: TenantScope):
    """Create the entry with the issued artifacts/status in a single transaction under the document row lock."""
    if not is_framework(document):
        return
    values = document.render_snapshot["values"]
    customer_id = document.render_snapshot["meta"]["customer_id"]
    number = values["document.official_full_number"]
    if not number or not await session.scalar(select(Customer.id).where(
        Customer.id == customer_id, Customer.tenant_id == scope.tenant_id,
    ).with_for_update()):
        raise ManagedDocumentConflictError("Для регистрации рамочного договора нужны проверенные номер и клиент")
    role, valid_until = _contract_facts(document)
    session.add(CustomerContract(
        customer_id=customer_id, legal_entity_id=document.legal_entity_id,
        source_document_id=document.id, number=number,
        valid_from=document.date, valid_until=valid_until, status="active", document_role_type=role,
    ))


async def archive_framework_contract(session: AsyncSession, document: OrderDocument):
    if document.doc_type == "contract":
        await session.execute(update(CustomerContract).where(
            CustomerContract.source_document_id == document.id
        ).values(status="archived"))


async def google_framework_basis(
    session: AsyncSession, *, order: Order, document: OrderDocument | None,
    contract: CustomerContract | None, issue_date: date,
) -> tuple[OrderDocument | None, CustomerContract | None]:
    """Resolve a mapped contract used with the system issuer's legacy templates."""
    if document is not None and is_framework(document):
        if document.status not in {"issued", "sent", "signed"}:
            raise ValueError("Выберите действующий выпущенный рамочный договор")
        lookup = select(CustomerContract).where(CustomerContract.source_document_id == document.id)
    elif contract is not None and (contract.legal_entity_id is not None or contract.source_document_id is not None):
        lookup = select(CustomerContract).where(CustomerContract.id == contract.id)
    else:
        return document, contract
    entry = await session.scalar(lookup.with_for_update().execution_options(populate_existing=True))
    if entry is None:
        raise ValueError("Рамочный договор ещё не зарегистрирован в карточке клиента")
    if (entry.customer_id != order.customer_id or entry.status != "active"
            or not entry.valid_from.date() <= issue_date <= entry.valid_until.date()):
        raise ValueError("Договор клиента недоступен на дату документа")
    default_issuer = await session.scalar(
        select(DocumentLegalEntity.id).join(Tenant, Tenant.id == DocumentLegalEntity.tenant_id).where(
            DocumentLegalEntity.id == entry.legal_entity_id, DocumentLegalEntity.tenant_id == order.tenant_id,
            DocumentLegalEntity.status == "active", DocumentLegalEntity.is_default.is_(True), Tenant.is_system.is_(True),
        )
    )
    if default_issuer is None:
        raise ValueError("Для юридического лица этого договора оформите документ в Документах CRM")
    return None, entry
