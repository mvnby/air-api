from dataclasses import replace
from datetime import date, datetime

import pytest
from sqlmodel import select

from models import Customer, CustomerBranch, CustomerContract, OrderDocument, OrderServiceLink
from models.tenancy import TenantScope
from modules.documents.application.context_builder import (
    DocumentContextBuilder, DocumentContextError, DocumentContextSelection,
)
from modules.documents.application.errors import ManagedDocumentConflictError
from modules.documents.application.open_contract_basis import validate_act_basis_for_issue
from modules.documents.domain import ActTerms
from services.customer_contract_service import CustomerContractService
from tests.integration.test_document_context_builder import _seed_order

SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


@pytest.mark.asyncio
async def test_partial_act_for_an_existing_client_contract_checks_site_dates_and_roles(db):
    order, issuer, selected, _ = await _seed_order(db)
    contract = CustomerContract(
        customer_id=order.customer_id, number="ОД-24",
        valid_from=datetime(2026, 4, 25), valid_until=datetime(2027, 4, 25),
    )
    branch = CustomerBranch(customer_id=order.customer_id, name="Магазин", delivery_address="ул. Полевая, 3")
    other = Customer(tenant_id=1, name="Другой клиент", phone="")
    db.add_all([contract, branch, other])
    await db.flush()
    other_branch = CustomerBranch(customer_id=other.id, name="Чужой объект", delivery_address="Другой адрес")
    db.add(other_branch)
    await db.flush()
    line = await db.scalar(select(OrderServiceLink).where(OrderServiceLink.proposal_id == selected.id))
    choice = DocumentContextSelection(
        order_id=order.id, legal_entity_id=issuer.id, proposal_id=selected.id,
        document_type="act", issue_date=date(2027, 4, 25), base_customer_contract_id=contract.id,
        scope_customer_branch_id=branch.id, scope_service_line_ids=(line.id,),
        scope_service_line_quantities={line.id: 1}, act_terms=ActTerms(claims_status="none"),
    )
    assert order.customer_contract_id is None
    assert CustomerContractService._to_item(contract)["document_role_type"] is None
    assert CustomerContractService.to_order_brief(contract)["document_role_type"] is None

    async def build(selection):
        return await DocumentContextBuilder.build(db, tenant_scope=SCOPE, selection=selection)

    with pytest.raises(DocumentContextError, match="названия сторон"):
        await build(choice)
    choice = replace(choice, document_role_type="executor_customer")
    snapshot = await build(choice)
    assert snapshot["meta"]["base_customer_contract_id"] == contract.id
    assert snapshot["meta"]["document_role_source"] == "explicit"
    assert snapshot["values"]["order.object_title"] == branch.name
    assert snapshot["values"]["order.object_address"] == branch.delivery_address
    assert snapshot["values"]["basis.number"] == contract.number
    rows = snapshot["table_rows"]["lines"]
    assert len(rows) == 1
    assert rows[0]["line.quantity"] == "1"
    assert rows[0]["line.amount"] == snapshot["values"]["totals.amount"]
    with pytest.raises(DocumentContextError, match="Объект"):
        await build(replace(choice, scope_customer_branch_id=other_branch.id))
    for outside in (date(2026, 4, 24), date(2027, 4, 26)):
        with pytest.raises(DocumentContextError, match="срок"):
            await build(replace(choice, issue_date=outside))

    draft = OrderDocument(order_id=order.id, doc_type="act", base_customer_contract_id=contract.id,
                          date=datetime(2027, 4, 25), render_snapshot=snapshot)
    await validate_act_basis_for_issue(db, document=draft, scope=SCOPE)
    snapshot["meta"]["document_role_source"] = "basis"
    with pytest.raises(ManagedDocumentConflictError, match="названия сторон"):
        await validate_act_basis_for_issue(db, document=draft, scope=SCOPE)
    contract.document_role_type = "executor_customer"
    await db.flush()
    await validate_act_basis_for_issue(db, document=draft, scope=SCOPE)
    contract.status = "archived"
    await db.flush()
    with pytest.raises(ManagedDocumentConflictError, match="недоступен"):
        await validate_act_basis_for_issue(db, document=draft, scope=SCOPE)
