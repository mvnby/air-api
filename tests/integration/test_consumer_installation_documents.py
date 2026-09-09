from datetime import date
from io import BytesIO

import pytest
from docx import Document
from sqlmodel import select

from models import OrderProductLink
from models.tenancy import TenantScope
from modules.documents.application import (
    ManagedDocumentConflictError, ManagedDocumentService, NativeTemplateVersionService,
)
from modules.documents.application.context_builder import (
    DocumentContextBuilder, DocumentContextError, DocumentContextSelection,
)
from modules.documents.application.native_template_discovery import discover_native_placeholder_contract
from modules.documents.domain import ConsumerDocumentTerms
from tests.integration.test_document_context_builder import _seed_order
from tests.integration.test_managed_document_lifecycle import _seed


@pytest.mark.asyncio
async def test_stage_split_uses_proposal_total_and_remains_an_immutable_obligation(db):
    order, issuer, selected, alternative = await _seed_order(db)
    issuer.requisites = {**issuer.requisites, "offer_url": "https://example.test/offer",
                         "offer_version": "1", "offer_published_on": "09.09.2026"}
    link = (await db.execute(select(OrderProductLink).where(
        OrderProductLink.proposal_id == selected.id,
    ))).scalar_one()
    link.price = 2740
    db.add_all([issuer, link])
    await db.commit()
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    selection = DocumentContextSelection(
        order_id=order.id, legal_entity_id=issuer.id,
        document_type="b2c_supply_installation_act", issue_date=date(2026, 9, 9),
        proposal_id=selected.id,
        consumer_terms=ConsumerDocumentTerms(
            installation_two_stages=True, installation_first_stage_amount="3000",
        ),
    )
    snapshot = await DocumentContextBuilder.build(db, tenant_scope=scope, selection=selection)
    assert snapshot["values"]["totals.amount"] == "3140.00"
    assert snapshot["values"]["installation.remaining_amount"] == "140.00"
    assert snapshot["conditions"]["installation.two_stages"] is True
    assert snapshot["conditions"]["installation.single_stage"] is False
    assert order.total_amount == 1400  # Document selection never rewrites the order/payment ledger.
    assert len(snapshot["table_rows"]["lines"]) == 2
    assert not any("альтернативный" in row["line.title"] for row in snapshot["table_rows"]["lines"])
    link.price = 2800
    db.add(link)
    await db.commit()
    assert snapshot["values"]["installation.remaining_amount"] == "140.00"
    with pytest.raises(DocumentContextError, match="меньше общей суммы"):
        await DocumentContextBuilder.build(db, tenant_scope=scope, selection=DocumentContextSelection(
            order_id=order.id, legal_entity_id=issuer.id,
            document_type="b2c_supply_installation_act", issue_date=date(2026, 9, 9),
            proposal_id=alternative.id, consumer_terms=selection.consumer_terms,
        ))


@pytest.mark.asyncio
async def test_staged_draft_cannot_silently_use_old_single_stage_template(db, tmp_path):
    scope, order, issuer, storage, _artifacts = await _seed(db, tmp_path)
    template = await NativeTemplateVersionService.create_template(
        db, tenant_scope=scope, legal_entity_id=issuer.id,
        name="Продажа с монтажом", doc_type="b2c_supply_installation_act",
    )
    doc = Document()
    doc.add_paragraph("Оборудование поставлено, все работы выполнены.")
    source = BytesIO()
    doc.save(source)
    version = await NativeTemplateVersionService.upload_native_docx_version(
        db, tenant_scope=scope, legal_entity_id=issuer.id, template_id=template.id,
        filename="old.docx", content=source.getvalue(), storage=storage,
        placeholder_contract=discover_native_placeholder_contract(source.getvalue()),
    )
    await NativeTemplateVersionService.activate_version(
        db, tenant_scope=scope, legal_entity_id=issuer.id,
        template_id=template.id, version_id=version.id,
    )
    with pytest.raises(ManagedDocumentConflictError, match="не поддерживает монтаж в два этапа"):
        await ManagedDocumentService.create_draft(
            db, tenant_scope=scope, template_id=template.id,
            selection=DocumentContextSelection(
                order_id=order.id, legal_entity_id=issuer.id,
                document_type="b2c_supply_installation_act", issue_date=date(2026, 9, 9),
                consumer_terms=ConsumerDocumentTerms(
                    installation_two_stages=True, installation_first_stage_amount="1360",
                ),
            ),
        )
