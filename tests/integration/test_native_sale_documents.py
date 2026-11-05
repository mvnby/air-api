from dataclasses import replace
from datetime import date, datetime
from io import BytesIO

from docx import Document
import pytest
from sqlmodel import select

from models import (
    Customer, CustomerEquipment, CustomerType, DocumentTemplate, EquipmentComponent, EquipmentOrderLink,
    EquipmentWarrantyCoverage, OrderDocument, OrderProductLink,
)
from models.tenancy import TenantScope
from modules.documents.application.context_builder import DocumentContextBuilder, DocumentContextError, DocumentContextSelection
from modules.documents.application.customer_readiness import check_selection_readiness
from modules.documents.application.lifecycle_service import ManagedDocumentService
from modules.documents.infrastructure.artifact_storage import PrivateDocumentArtifactStorage
from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
from services.document_service import DocumentService
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from tests.integration.test_document_context_builder import _seed_order
from tests.integration.test_managed_document_lifecycle import FakePdfConverter

SCOPE = TenantScope(tenant_id=1, storefront_id=1)


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "series", "individual"), [
    ("retail_receipt", "ТЧ", True), ("warranty_certificate", "ГТ", False), ("warranty_certificate", "ГТ", True),
])
async def test_sale_documents_issue_from_frozen_verified_facts(db, tmp_path, kind, series, individual):
    order, issuer, proposal, other = await _seed_order(db)
    if individual:
        buyer = await db.get(Customer, order.customer_id)
        buyer.name, buyer.full_legal_name, buyer.type, buyer.inn = "Покупатель", "", CustomerType.individual, None
        issuer.requisites = {"offer_url": "https://offer.example.test", "offer_version": "7", "offer_published_on": "01.05.2026"}
    product_id = await db.scalar(select(OrderProductLink.product_id).where(OrderProductLink.proposal_id == proposal.id))
    equipment = CustomerEquipment(
        customer_id=order.customer_id, catalog_product_id=product_id, source_order_id=order.id,
        equipment_source="sold_by_us", model="Split 48", serial="MAIN-48", location_hint="Офис 4",
        warranty_started_at=datetime(2026, 6, 4), warranty_expires_at=datetime(2027, 6, 4),
    )
    db.add(equipment)
    await db.flush()
    coverage = EquipmentWarrantyCoverage(
        equipment_id=equipment.id, coverage_type="supplier", starts_at=datetime(2026, 6, 5),
        expires_at=datetime(2030, 6, 5), terms_snapshot="Срок по паспорту данной модели",
    )
    db.add_all([coverage, EquipmentComponent(equipment_id=equipment.id, title="Наружный блок", serial="OUT-48"),
                EquipmentComponent(equipment_id=equipment.id, title="Снятый блок", serial="REMOVED", is_archived=True)])
    for suffix in ("008", "002", "ручной"):
        db.add(OrderDocument(order_id=order.id, doc_type=kind, number=f"{series}-2026-{suffix}"))
    await db.commit()
    assert await DocumentService._get_next_number(db, kind, datetime(2026, 6, 6), tenant_id=1) == f"{series}-2026-009"
    private = LocalPrivateAttachmentStorage(tmp_path / "private")
    storage = PrivateTemplateSourceStorage(private)
    selection = DocumentContextSelection(order_id=order.id, legal_entity_id=issuer.id, document_type=kind,
        issue_date=date(2026, 6, 6), proposal_id=proposal.id, receipt_note="Пуск после отделки" if kind == "retail_receipt" else None,
        warranty_equipment_id=equipment.id if kind == "warranty_certificate" else None)
    if kind == "warranty_certificate":
        with pytest.raises(DocumentContextError, match="предложени"):
            await DocumentContextBuilder.build(db, tenant_scope=SCOPE, selection=replace(selection, proposal_id=other.id))
    readiness = await check_selection_readiness(db, tenant_scope=SCOPE, selection=selection, template_id=None, template_storage=storage)
    assert readiness == {"checked": True, "missing_fields": [], "can_issue": True, "template_id": None, "template_version_id": None}
    assert await db.scalar(select(DocumentTemplate.id).where(DocumentTemplate.doc_type == kind)) is None
    draft = await ManagedDocumentService.create_draft(db, tenant_scope=SCOPE, selection=selection, template_storage=storage)
    assert not draft.official_number
    coverage.terms_snapshot = "Изменено после черновика"
    equipment.serial = "REPLACED-48"
    await db.commit()
    result = await ManagedDocumentService.issue(db, tenant_scope=SCOPE, document_id=draft.id, template_storage=storage,
        artifact_storage=PrivateDocumentArtifactStorage(private), pdf_converter=FakePdfConverter())
    assert result.document.render_snapshot["values"]["document.official_full_number"] == f"{series}-2026-009"
    assert await DocumentService._get_next_number(db, kind, datetime(2026, 6, 6), tenant_id=1) == f"{series}-2026-010"
    artifact = next(item for item in result.artifacts if item.kind == "rendered_docx")
    content = await private.read(artifact.storage_key)
    doc = Document(BytesIO(content))
    paragraphs = "\n".join(p.text for p in doc.paragraphs)
    assert "Покупатель" in paragraphs and "Мастер Воздуха" in paragraphs
    assert ("offer.example.test" in paragraphs) == individual
    assert "{{" not in paragraphs
    if kind == "warranty_certificate":
        for fact in ("объект покупателя, Офис 4", "Split 48", "MAIN-48", "OUT-48", "05.06.2026", "05.06.2030", "по паспорту"):
            assert fact in paragraphs
        assert all(bad not in paragraphs for bad in ("REMOVED", "REPLACED", "Изменено"))
    else:
        table = [[c.text for c in row.cells] for row in doc.tables[0].rows]
        assert len(table) == 3 and "выбранный" in table[1][0] and "Монтаж" in table[2][0] and table[2][1] == "2"
        assert "Пуск после отделки" in paragraphs
        assert "Итого:1400.00BYN" in paragraphs.replace(" ", "").replace(",", ".")
        assert all(bad not in paragraphs.lower() for bad in ("оплачено", "работы выполнены", "36 мес"))
    await ManagedDocumentService.create_draft(db, tenant_scope=SCOPE, selection=selection, template_storage=storage)
    assert len(list(await db.scalars(select(DocumentTemplate.id).where(DocumentTemplate.doc_type == kind)))) == 1


@pytest.mark.asyncio
async def test_sale_selection_rejects_unverified_sources(db):
    order, issuer, proposal, _ = await _seed_order(db)
    form = DocumentContextSelection(order_id=order.id, legal_entity_id=issuer.id, document_type="retail_receipt",
                                   issue_date=date(2026, 6, 6), proposal_id=proposal.id)
    async def rejected(selection, message):
        with pytest.raises(DocumentContextError, match=message):
            await DocumentContextBuilder.build(db, tenant_scope=SCOPE, selection=selection)
    await rejected(form, "физического лица")
    with pytest.raises(DocumentContextError, match="физического лица"):
        await check_selection_readiness(db, tenant_scope=SCOPE, selection=form, template_id=None, template_storage=None)
    buyer = await db.get(Customer, order.customer_id)
    buyer.type, buyer.inn, buyer.full_legal_name, buyer.name = CustomerType.individual, None, "", "Покупатель"
    await db.commit()
    await rejected(form, "оферты")
    product = await db.scalar(select(OrderProductLink.product_id).where(OrderProductLink.proposal_id == proposal.id))
    unit = CustomerEquipment(customer_id=order.customer_id, model="Unit", catalog_product_id=product,
                             warranty_started_at=datetime(2026,5,1), warranty_expires_at=datetime(2028,5,1))
    db.add(unit)
    await db.flush()
    permit = replace(form, document_type="warranty_certificate", warranty_equipment_id=unit.id)
    await rejected(permit, "этой продажи")
    unit.source_order_id = order.id
    db.add(EquipmentOrderLink(equipment_id=unit.id, order_id=order.id, role="maintenance"))
    await db.flush()
    await rejected(permit, "этой продажи")
    db.add(EquipmentOrderLink(equipment_id=unit.id, order_id=order.id, role="sale"))
    db.add(EquipmentWarrantyCoverage(equipment_id=unit.id, coverage_type="mvn_work"))
    await db.flush()
    await rejected(permit, "покрытия оборудования")
    coverage = EquipmentWarrantyCoverage(equipment_id=unit.id, coverage_type="supplier", decision_status="voided")
    db.add(coverage)
    await db.flush()
    await rejected(permit, "покрытие")
    coverage.decision_status = "none"
    coverage.starts_at, coverage.expires_at = unit.warranty_started_at, unit.warranty_expires_at
    coverage.maintenance_required, coverage.next_maintenance_due_at = True, datetime(2026, 6, 1)
    await db.flush()
    await rejected(permit, "решение менеджера")
    unit_component = EquipmentComponent(equipment_id=unit.id, title="Блок")
    db.add(unit_component)
    await db.flush()
    db.add(EquipmentWarrantyCoverage(equipment_id=unit.id, component_id=unit_component.id, coverage_type="supplier"))
    await db.flush()
    await rejected(permit, "отдельные гарантийные покрытия")
