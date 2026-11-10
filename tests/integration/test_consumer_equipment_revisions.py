"""A replacement continues the saved work, including pre-typed legacy snapshots."""

from copy import deepcopy
from dataclasses import replace
from datetime import date

import pytest
from sqlmodel import select

from models import Customer, CustomerEquipment, CustomerType, OrderServiceLink, OrderProposal, Service
from modules.documents.application import ManagedDocumentService
from modules.documents.application.context_builder import DocumentContextSelection
from modules.documents.application.context_builder import DocumentContextBuilder, DocumentContextError
from modules.documents.application.draft_mutations import ManagedDocumentDraftMutationService
from modules.documents.application.errors import ManagedDocumentConflictError
from modules.documents.api.draft_selection import selection_from_payload
from modules.documents.api.schemas import ManagedDocumentDraftPayload
from modules.documents.domain import ConsumerDocumentTerms
from tests.integration.test_managed_document_lifecycle import _seed


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("equipment_source", ["customer_owned", "sold_by_us"])
@pytest.mark.parametrize("empty_form", [False, True])
async def test_date_only_replacement_inherits_frozen_equipment_and_lines(db, tmp_path, legacy, equipment_source, empty_form):
    kind = "b2c_customer_equipment_installation_act"
    scope, order, issuer, storage, _ = await _seed(db, tmp_path, document_type=kind)
    customer = await db.get(Customer, order.customer_id)
    customer.type = CustomerType.individual
    issuer.requisites = {"offer_url": "https://example.test/offer", "offer_version": "1",
                         "offer_published_on": "01.11.2026"}
    service = Service(title="Тестовый монтаж", slug="revision-test-install", base_price=600)
    db.add_all([customer, issuer, service])
    await db.flush()
    proposal_id = await db.scalar(select(OrderProposal.id).where(OrderProposal.order_id == order.id))
    line = OrderServiceLink(order_id=order.id, proposal_id=proposal_id, service_id=service.id, title=service.title,
                            quantity=1, price=600, cost=0)
    db.add(line)
    equipment = CustomerEquipment(customer_id=order.customer_id, source_order_id=order.id,
        equipment_source=equipment_source, brand="TEST", model="TEST-09", serial="TEST-SN-001")
    db.add(equipment)
    await db.commit()
    selection = DocumentContextSelection(
        order_id=order.id, legal_entity_id=issuer.id, document_type=kind,
        issue_date=date(2026, 11, 1), scope_product_line_ids=(),
        consumer_terms=ConsumerDocumentTerms(equipment_id=equipment.id, equipment_brand="TEST", equipment_model="TEST-09",
            equipment_serial="TEST-SN-001", work_warranty_months=19, route_notes="Известные условия"),
    )
    original = await ManagedDocumentService.create_draft(db, tenant_scope=scope, selection=selection,
                                                        template_storage=storage)
    # Issuance itself is covered by lifecycle/rendering tests; freeze this source as issued.
    original.status = "issued"
    if legacy:
        snapshot = deepcopy(original.render_snapshot)
        snapshot["meta"]["draft_parameters"].pop("consumer_terms")
        original.render_snapshot = snapshot
    db.add(original)
    await db.commit()
    original_id = original.id
    issuer_id, order_id, equipment_id = issuer.id, order.id, equipment.id
    frozen = deepcopy(original.render_snapshot)
    assert frozen["values"]["totals.amount"] == "600.00"
    # Reload with no frontend state; the live commercial offer has since changed.
    line.price = 900
    equipment.model = "CHANGED-18"
    equipment.serial = "CHANGED-SERIAL"
    db.add_all([line, equipment])
    await db.commit()
    db.expire_all()
    next_selection = replace(selection, issue_date=date(2026, 11, 2), consumer_terms=None)
    if legacy and not empty_form:
        # Saving a legacy snapshot to a registry unit is an explicit association,
        # not consent to replace historical facts with that card's later changes.
        next_selection = replace(next_selection, consumer_terms=ConsumerDocumentTerms(
            equipment_id=equipment_id, equipment_brand="TEST", equipment_model="TEST-09", equipment_serial="TEST-SN-001"),
            consumer_terms_fields=frozenset({"equipment_id", "equipment_brand", "equipment_model", "equipment_serial"}))
    if empty_form:
        next_selection = selection_from_payload(order_id, ManagedDocumentDraftPayload(
            legal_entity_id=issuer_id, document_type=kind, issue_date=date(2026, 11, 2),
            replaces_document_id=original_id, consumer_terms={"equipment_model": None,
                "equipment_serial": None, "goods_warranty_months": 36, "work_warranty_months": 12}))
    replacement = await ManagedDocumentService.create_draft(db, tenant_scope=scope,
        selection=next_selection,
        replaces_document_id=original_id, template_storage=storage)
    assert replacement.render_snapshot["values"]["equipment.model"] == "TEST-09"
    assert replacement.render_snapshot["values"]["equipment.serial"] == "TEST-SN-001"
    assert replacement.render_snapshot["values"]["warranty.work.months"] == "19"
    assert replacement.render_snapshot["table_rows"] == frozen["table_rows"]
    assert replacement.render_snapshot["values"]["totals.amount"] == "600.00"
    parameters = await ManagedDocumentDraftMutationService.get(db, tenant_scope=scope,
                                                               document_id=replacement.id)
    changed = await ManagedDocumentDraftMutationService.update(db, tenant_scope=scope,
        document_id=replacement.id, expected_revision=parameters["revision"],
        changes={"issue_date": "2026-11-03"})
    assert changed.render_snapshot["values"]["equipment.serial"] == "TEST-SN-001"
    assert changed.render_snapshot["table_rows"] == frozen["table_rows"]
    with pytest.raises(ManagedDocumentConflictError, match="другой вкладке"):
        await ManagedDocumentDraftMutationService.update(db, tenant_scope=scope,
            document_id=replacement.id, expected_revision=parameters["revision"], changes={"issue_date": "2026-11-04"})
    parameters = await ManagedDocumentDraftMutationService.get(db, tenant_scope=scope, document_id=replacement.id)
    corrected = await ManagedDocumentDraftMutationService.update(db, tenant_scope=scope,
        document_id=replacement.id, expected_revision=parameters["revision"], changes={"consumer_terms": {"route_notes": "Поправка"}})
    assert corrected.render_snapshot["values"]["equipment.serial"] == "TEST-SN-001"
    assert (await ManagedDocumentService.get_document(db, tenant_scope=scope,
                                                      document_id=original_id)).render_snapshot == frozen


@pytest.mark.asyncio
async def test_document_selection_rejects_foreign_unlinked_and_archived_equipment(db, tmp_path):
    kind = "b2c_customer_equipment_installation_act"
    scope, order, issuer, _, _ = await _seed(db, tmp_path, document_type=kind)
    issuer.requisites = {"offer_url": "https://example.test/offer", "offer_version": "1", "offer_published_on": "01.11.2026"}
    proposal_id = await db.scalar(select(OrderProposal.id).where(OrderProposal.order_id == order.id))
    other = Customer(tenant_id=1, name="TEST other customer", phone="")
    db.add(other)
    await db.flush()
    units = [CustomerEquipment(customer_id=other.id, source_order_id=order.id, model="FOREIGN"),
             CustomerEquipment(customer_id=order.customer_id, model="UNLINKED"),
             CustomerEquipment(customer_id=order.customer_id, source_order_id=order.id, model="ARCHIVED", is_archived=True)]
    db.add_all([issuer, *units, OrderServiceLink(order_id=order.id, proposal_id=proposal_id, title="TEST монтаж", quantity=1, price=600)])
    await db.commit()
    for unit in units:
        with pytest.raises(DocumentContextError, match="оборудование"):
            await DocumentContextBuilder.build(db, tenant_scope=scope, selection=DocumentContextSelection(
                order_id=order.id, legal_entity_id=issuer.id, document_type=kind, issue_date=date(2026, 11, 10),
                scope_product_line_ids=(), consumer_terms=ConsumerDocumentTerms(equipment_id=unit.id)))
