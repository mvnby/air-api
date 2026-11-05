"""Service contract snapshots use native lifecycle and detect later edits."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.command_actor import CommandActor
from models import Customer, Order, OrderDocument, OrderProductLink, OrderProposal, OrderServiceLink
from modules.documents.application import ManagedDocumentService
from modules.documents.application.errors import ManagedDocumentConflictError
from modules.documents.application.draft_mutations import ManagedDocumentDraftMutationService
from schemas_connector_service_order_document import (
    ServiceOrderContractPrepareInput,
    ServiceOrderContractReadInput,
)
from services.connector_service_order_document import get_service_order_contract, prepare_service_order_contract
from services.order_proposal_version import proposal_version
from tests.integration.test_managed_document_lifecycle import FakePdfConverter, _seed


@pytest.fixture
async def document_db(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        yield session


async def _setup(db, tmp_path, document_type="contract"):
    scope, order, issuer, storage, artifacts = await _seed(db, tmp_path, document_type=document_type)
    proposal = (
        (await db.execute(select(OrderProposal).where(OrderProposal.order_id == order.id))).scalars().one()
    )
    for product in (
        await db.execute(select(OrderProductLink).where(OrderProductLink.order_id == order.id))
    ).scalars():
        await db.delete(product)
    line = OrderServiceLink(
        order_id=order.id,
        proposal_id=proposal.id,
        title="Комплексный ремонт",
        description="Диагностика, замена компрессора и пусконаладка",
        quantity=1,
        price=Decimal("1030.00"),
    )
    db.add(line)
    order.workflow_type = "repair"
    db.add(order)
    await db.commit()
    actor = CommandActor(1, "test", scope, "chatgpt")
    version = await proposal_version(db, order.id, proposal.id)
    inputs = ServiceOrderContractPrepareInput(
        order_id=order.id,
        proposal_id=proposal.id,
        expected_version=version,
        legal_entity_id=issuer.id,
        issue_date=date(2026, 11, 5),
        idempotency_key="test-contract-draft-key-0001",
    )
    return actor, inputs, storage, artifacts, line


@pytest.mark.asyncio
async def test_contract_freezes_selected_service_and_blocks_stale_issue(document_db, tmp_path):
    db = document_db
    actor, inputs, storage, artifacts, line = await _setup(db, tmp_path)
    result = await prepare_service_order_contract(db, actor, inputs, template_storage=storage)
    assert (
        result.status == "draft"
        and result.customer_ready_and_current
        and not result.stale
        and result.readiness.can_issue
    )
    assert f"documentId={result.document_id}" in result.manager_url
    doc = await db.get(OrderDocument, result.document_id)
    assert doc.official_number is None and doc.google_file_id is None
    rows = doc.render_snapshot["table_rows"]["lines"]
    assert len(rows) == 1 and rows[0]["line.amount"] == "1030.00"
    assert "замена компрессора" in rows[0]["line.title"]
    assert rows[0]["line.quantity"] == "1" and rows[0]["line.unit"] == "шт."
    parameters = await ManagedDocumentDraftMutationService.get(
        db, tenant_scope=actor.tenant_scope, document_id=doc.id
    )
    await ManagedDocumentDraftMutationService.update(
        db,
        tenant_scope=actor.tenant_scope,
        document_id=doc.id,
        changes={"issue_city": "Минск"},
        expected_revision=parameters["revision"],
    )
    current = await get_service_order_contract(
        db, actor, ServiceOrderContractReadInput(document_id=doc.id), template_storage=storage
    )
    assert not current.stale and current.readiness.can_issue
    parameters = await ManagedDocumentDraftMutationService.get(
        db, tenant_scope=actor.tenant_scope, document_id=doc.id
    )
    terms = parameters["business_terms"]
    terms["payment_schedule"][0]["due_event"] = "after_work"
    await ManagedDocumentDraftMutationService.update(
        db,
        tenant_scope=actor.tenant_scope,
        document_id=doc.id,
        changes={"business_terms": terms},
        expected_revision=parameters["revision"],
    )
    current = await get_service_order_contract(
        db, actor, ServiceOrderContractReadInput(document_id=doc.id), template_storage=storage
    )
    assert not current.stale and current.payment_terms != result.payment_terms
    line.price = Decimal("1100.00")
    db.add(line)
    await db.flush()
    current = await get_service_order_contract(
        db, actor, ServiceOrderContractReadInput(document_id=doc.id), template_storage=storage
    )
    assert (
        current.stale
        and not current.customer_ready_and_current
        and current.current_proposal_version != current.proposal_version
    )
    with pytest.raises(ManagedDocumentConflictError, match="Предложение изменилось"):
        await ManagedDocumentService.issue(
            db,
            tenant_scope=actor.tenant_scope,
            document_id=doc.id,
            template_storage=storage,
            artifact_storage=artifacts,
            pdf_converter=FakePdfConverter(),
        )
    assert doc.official_number is None


@pytest.mark.asyncio
async def test_missing_customer_data_reports_fields_and_outdated_input_rejected(document_db, tmp_path):
    db = document_db
    actor, inputs, storage, _, line = await _setup(db, tmp_path)
    order = await db.get(Order, inputs.order_id)
    customer = await db.get(Customer, order.customer_id)
    customer.name = ""
    customer.full_legal_name = ""
    db.add(customer)
    await db.flush()
    result = await prepare_service_order_contract(db, actor, inputs, template_storage=storage)
    assert result.customer_ready_and_current and result.readiness.can_issue
    assert any(field.field == "customer.full_name" for field in result.readiness.missing_fields)
    line.price = Decimal("1100.00")
    db.add(line)
    await db.flush()
    with pytest.raises(ManagedDocumentConflictError, match="Proposal changed"):
        await prepare_service_order_contract(db, actor, inputs, template_storage=storage)


@pytest.mark.asyncio
async def test_foreign_issuer_and_unrelated_native_document_are_not_exposed(document_db, tmp_path):
    db = document_db
    actor, inputs, storage, _, _ = await _setup(db, tmp_path)
    with pytest.raises(HTTPException) as error:
        await prepare_service_order_contract(
            db, actor, inputs.model_copy(update={"legal_entity_id": 999999}), template_storage=storage
        )
    assert error.value.status_code == 404
    result = await prepare_service_order_contract(db, actor, inputs, template_storage=storage)
    document = await db.get(OrderDocument, result.document_id)
    snapshot = dict(document.render_snapshot)
    snapshot["meta"] = {
        key: value for key, value in snapshot["meta"].items() if key != "connector_proposal_version"
    }
    document.render_snapshot = snapshot
    db.add(document)
    await db.flush()
    with pytest.raises(HTTPException) as error:
        await get_service_order_contract(
            db, actor, ServiceOrderContractReadInput(document_id=document.id), template_storage=storage
        )
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_native_invoice_offer_uses_selected_proposal_and_does_not_issue(document_db, tmp_path):
    db = document_db
    actor, inputs, storage, _, _ = await _setup(db, tmp_path, document_type="invoice")
    inputs = inputs.model_copy(update={"document_type": "invoice", "business_role": "offer"})
    result = await prepare_service_order_contract(db, actor, inputs, template_storage=storage)
    document = await db.get(OrderDocument, result.document_id)
    assert result.business_role == "offer" and document.business_role == "offer"
    assert document.base_document_id is None and document.official_number is None
    assert document.proposal_id == inputs.proposal_id
    assert document.render_snapshot["table_rows"]["lines"][0]["line.amount"] == "1030.00"
    assert result.readiness.checked and result.customer_ready_and_current
