from copy import deepcopy
from datetime import date
from io import BytesIO

from docx import Document
import pytest
from sqlmodel import select

from models import DocumentTemplate, OrderDocument, OrderProductLink, OrderProposal
from modules.documents.application import (
    DocumentContextSelection, ManagedDocumentService, NativeTemplatePlaceholderContract,
    NativeTemplateVersionService,
)
from modules.documents.application.draft_preview import ManagedDocumentDraftPreviewService
from modules.documents.infrastructure.renderers import TableBlockSpec
from tests.integration.test_managed_document_lifecycle import FakePdfConverter, _seed
from tests.integration.test_manager_document_draft_parameters_api import BASE, _legacy_owner_headers


@pytest.mark.asyncio
async def test_ttn_cargo_uses_frozen_shipment_rows_and_prints_verified_totals(async_client, db, tmp_path):
    headers = await _legacy_owner_headers(async_client)
    scope, order, issuer, templates, files = await _seed(db, tmp_path, document_type="ttn1")
    proposal = await db.scalar(select(OrderProposal).where(OrderProposal.order_id == order.id))
    link = await db.scalar(select(OrderProductLink).where(OrderProductLink.proposal_id == proposal.id))
    link.quantity = 2
    link.logistics_components = [
        {"title": "Внутренний блок", "quantity_per_parent": 2, "unit_price": 250},
        {"title": "Наружный блок", "quantity_per_parent": 1, "unit_price": 1000},
    ]
    basis = OrderDocument(tenant_id=1, legal_entity_id=issuer.id, order_id=order.id, proposal_id=proposal.id,
                          doc_type="contract", status="issued", number="Д-112", internal_reference="doc_cargo_basis")
    db.add(basis)
    await db.commit()
    # Active, editable company template reading real cargo figures separately from goods quantities.
    form = Document()
    form.add_paragraph("Места {{ totals.seats }} · {{ totals.seats_in_words }}")
    form.add_paragraph("Масса {{ totals.weight }} · {{ totals.weight_in_words }}")
    table = form.add_table(rows=1, cols=4)
    for cell, token in zip(table.rows[0].cells, ("{{ lines }}{{ line.title }}", "{{ line.quantity }}",
                                                 "{{ line.seats }}", "{{ line.mass }}"), strict=True):
        cell.text = token
    blob = BytesIO()
    form.save(blob)
    template = await db.scalar(select(DocumentTemplate).where(DocumentTemplate.doc_type == "ttn1"))
    version = await NativeTemplateVersionService.upload_native_docx_version(
        db, tenant_scope=scope, legal_entity_id=issuer.id, template_id=template.id,
        filename="Отгрузка.docx", content=blob.getvalue(), storage=templates,
        placeholder_contract=NativeTemplatePlaceholderContract.create(
            field_catalog={"totals.seats", "totals.seats_in_words", "totals.weight", "totals.weight_in_words"},
            table_blocks=(TableBlockSpec(name="lines", row_fields=frozenset(
                {"line.title", "line.quantity", "line.seats", "line.mass"})),),
        ),
    )
    await NativeTemplateVersionService.activate_version(db, tenant_scope=scope, legal_entity_id=issuer.id,
                                                       template_id=template.id, version_id=version.id)
    draft = await ManagedDocumentService.create_draft(
        db, tenant_scope=scope, template_storage=templates,
        selection=DocumentContextSelection(order_id=order.id, legal_entity_id=issuer.id, document_type="ttn1",
            proposal_id=proposal.id, scope_product_line_ids=(link.id,), base_document_id=basis.id, issue_date=date(2026, 11, 6)),
    )
    assert draft.render_snapshot["values"]["totals.weight"] == ""
    assert draft.render_snapshot["table_rows"]["lines"][0]["line.seats"] == ""
    # Simulate an older saved draft whose renderer used product count and hardcoded zero.
    old = deepcopy(draft.render_snapshot)
    old["values"].pop("totals.seats")
    old["values"].pop("totals.seats_in_words")
    old["values"]["totals.weight"] = "0"
    for row in old["table_rows"]["lines"]:
        row.update({"line.seats": row["line.quantity"], "line.mass": "0.00"})
    draft.render_snapshot = old
    link.quantity = 9
    await db.commit()
    class PreviewConverter(FakePdfConverter):
        def convert_docx(self, content, *, filename):
            preview = Document(BytesIO(content))
            assert all(row.cells[2].text == row.cells[3].text == "" for row in preview.tables[0].rows)
            return super().convert_docx(content, filename=filename)

    await ManagedDocumentDraftPreviewService.render_pdf(
        db, tenant_scope=scope, document_id=draft.id, template_storage=templates, artifact_storage=files,
        pdf_converter=PreviewConverter(),
    )
    assert draft.render_snapshot["table_rows"]["lines"][0]["line.mass"] == "0.00"
    url = f"{BASE}/documents/{draft.id}/draft/parameters"
    params = (await async_client.get(url, headers=headers)).json()
    assert [(r["quantity"], r["seats"], r["mass_kg"]) for r in params["waybill_cargo"]] == [("4", None, None), ("2", None, None)]
    async def update(measures, revision=None):
        return await async_client.patch(url, headers=headers, json={
            "expected_revision": revision or params["revision"], "waybill_cargo": measures,
        })
    first = {"line_number": 1, "seats": 1, "mass_kg": "34.5"}
    second = {"line_number": 2, "seats": 2, "mass_kg": None}
    assert (await update([first, first])).status_code == 400
    assert (await update([first, {**second, "line_number": 3}])).status_code == 400
    assert (await update([first])).status_code == 400
    assert (await update([first, {**second, "mass_kg": "-5"}])).status_code == 422
    assert (await update([first, {**second, "seats": 1.5}])).status_code == 422
    assert (await update([first, second])).status_code == 200
    await db.refresh(draft)
    assert draft.render_snapshot["values"]["totals.weight"] == ""
    assert draft.render_snapshot["values"]["totals.seats"] == "3"
    assert draft.render_snapshot["table_rows"]["lines"][1]["line.mass"] == ""
    assert (await update([first, {**second, "mass_kg": "54.5"}])).status_code == 409
    params = (await async_client.get(url, headers=headers)).json()
    assert params["waybill_cargo"][0]["mass_kg"] == "34.5"
    assert (await update([{**second, "mass_kg": "54.5"}, first])).status_code == 200
    await db.refresh(draft)
    assert draft.render_snapshot["values"]["totals.quantity"] == "6"
    result = await ManagedDocumentService.issue(db, tenant_scope=scope, document_id=draft.id, template_storage=templates,
        artifact_storage=files, pdf_converter=FakePdfConverter())
    stored = next(a for a in result.artifacts if a.kind == "rendered_docx")
    printed = Document(BytesIO(await files.read(ManagedDocumentService.stored_artifact(stored))))
    assert [p.text for p in printed.paragraphs] == ["Места 3 · три", "Масса 89 · восемьдесят девять"]
    assert [[c.text for c in r.cells] for r in printed.tables[0].rows] == [
        ["Внутренний блок", "4", "1", "34.5"], ["Наружный блок", "2", "2", "54.5"]]
    assert (await update([first, second])).status_code == 409
