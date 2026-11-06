from datetime import date
from importlib import import_module
from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfWriter
import pytest
from sqlmodel import select

from models import DocumentTemplate, DocumentTemplateVersion, OrderDocument, OrderProposal, Tenant
from modules.documents.application import (
    DocumentContextSelection,
    ManagedDocumentConflictError,
    ManagedDocumentService,
)
from modules.documents.application.waybill_paper import validate_stock_pdf
from modules.documents.application.editable_draft_issue import verify_document_external_edit_before_issue
from modules.documents.application.managed_document_external_edits import (
    ManagedDocumentExternalEditSessionService,
)
from tests.integration.test_managed_document_google_editing import FakeGoogleEditor
from modules.documents.domain import TransportTerms
from modules.documents.domain.transport_terms import TransportOperation
from scripts.manage_native_document_template_bundle import (
    BundleError,
    apply_bundle,
    inspect_bundle,
    load_bundle,
    prepare_sources,
)
from scripts.prepare_mvn_waybill_templates import prepare
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from tests.integration.test_managed_document_lifecycle import _seed, FakePdfConverter


MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "config/native_document_template_bundles/mvn-paper-waybills-v1.json"
)


class StockConverter(FakePdfConverter):
    def __init__(self, pages=1):
        self.pages = pages
        self.calls = 0

    def convert_docx(self, content, *, filename):
        super().convert_docx(content, filename=filename)
        writer = PdfWriter()
        for _ in range(self.pages):
            writer.add_blank_page(595.28, 841.89)
        buf = BytesIO()
        writer.write(buf)
        self.calls += 1
        return buf.getvalue()


@pytest.mark.asyncio
async def test_targeted_forms_install_then_issue_without_overwriting_custom_template(
    db, tmp_path, monkeypatch
):
    scope, order, issuer, template_storage, artifacts = await _seed(db, tmp_path, document_type="ttn1")
    tenant = await db.get(Tenant, scope.tenant_id)
    tenant.slug = "mvn"
    issuer.is_vat_payer = False
    await db.commit()
    src = tmp_path / "paper"
    prepare(src)
    bundle = load_bundle(MANIFEST)
    prepared = prepare_sources(bundle, src)
    monkeypatch.setattr(
        import_module("modules.documents.api.router"),
        "get_private_attachment_storage",
        lambda: LocalPrivateAttachmentStorage(tmp_path / "private-documents"),
    )
    custom = await db.scalar(select(DocumentTemplate).where(DocumentTemplate.doc_type == "ttn1"))
    before = await db.scalar(
        select(DocumentTemplateVersion.checksum_sha256).where(
            DocumentTemplateVersion.template_id == custom.id
        )
    )
    _, plan = await inspect_bundle(db, tenant_id=scope.tenant_id, legal_entity_id=issuer.id, bundle=bundle)
    assert all(item["template_action"] == "create" for item in plan)
    await apply_bundle(db, scope=scope, legal_entity_id=issuer.id, bundle=bundle, prepared=prepared)
    _, plan = await inspect_bundle(db, tenant_id=scope.tenant_id, legal_entity_id=issuer.id, bundle=bundle)
    assert all(item["template_action"] == item["version_action"] == "keep" for item in plan)
    assert before == await db.scalar(
        select(DocumentTemplateVersion.checksum_sha256).where(
            DocumentTemplateVersion.template_id == custom.id
        )
    )
    proposal = await db.scalar(select(OrderProposal).where(OrderProposal.order_id == order.id))
    basis = OrderDocument(
        tenant_id=scope.tenant_id,
        legal_entity_id=issuer.id,
        order_id=order.id,
        proposal_id=proposal.id,
        doc_type="contract",
        status="issued",
        number="Д-024",
        internal_reference="sample_basis_waybill",
    )
    db.add(basis)
    await db.commit()

    for spec in bundle.templates:
        template = await db.scalar(select(DocumentTemplate).where(DocumentTemplate.name == spec.name))
        truck = spec.doc_type == "ttn1"
        args = dict(
            order_id=order.id,
            legal_entity_id=issuer.id,
            document_type=spec.doc_type,
            proposal_id=proposal.id,
            base_document_id=basis.id,
            issue_date=date(2026, 11, 6),
        )
        if truck:
            args["transport_terms"] = TransportTerms(
                loading_point="Учебный склад",
                freight_payer_unp="900000003",
                loading=TransportOperation(arrived_at="2026-11-06T08:10", departed_at="2026-11-06T08:35"),
            )
        selection = DocumentContextSelection(**args)
        draft = await ManagedDocumentService.create_draft(
            db,
            tenant_scope=scope,
            template_storage=template_storage,
            template_id=template.id,
            selection=selection,
        )
        verified = None
        if truck:
            provider = FakeGoogleEditor()
            await ManagedDocumentExternalEditSessionService.ensure_session(
                db,
                tenant_scope=scope,
                document_id=draft.id,
                template_storage=template_storage,
                artifact_storage=artifacts,
                provider=provider,
            )
            verified = await verify_document_external_edit_before_issue(
                db, tenant_scope=scope, document_id=draft.id, provider=provider
            )
        too_long = StockConverter(pages=2)
        with pytest.raises(ManagedDocumentConflictError, match="2 стр"):
            await ManagedDocumentService.issue(
                db,
                tenant_scope=scope,
                template_storage=template_storage,
                artifact_storage=artifacts,
                document_id=draft.id,
                pdf_converter=too_long,
                verified_remote_revision=verified,
            )
        await db.refresh(draft)
        assert draft.status == "draft" and draft.official_number is None
        complete = StockConverter()
        issued = await ManagedDocumentService.issue(
            db,
            tenant_scope=scope,
            template_storage=template_storage,
            artifact_storage=artifacts,
            document_id=draft.id,
            pdf_converter=complete,
            verified_remote_revision=verified,
        )
        assert complete.calls == 1
        artifact = next(a for a in issued.artifacts if a.kind == "rendered_docx")
        doc = Document(BytesIO(await artifacts.read(ManagedDocumentService.stored_artifact(artifact))))
        rows = [c.text for t in doc.tables for r in t.rows for c in r.cells]
        text = " ".join(rows)
        assert not any(x in text for x in ("{{", "}}", "None"))
        for token in ("Д-024", "Продавец", "Клиент", "Кондиционер", "1500.00", "без НДС"):
            assert token in text
        assert "Китай" not in text  # Catalog and saved component do not supply a country.
        assert str(issued.document.official_number) and issued.document.status == "issued"
        if truck:
            for token in ("900000003", "Учебный склад", "06.11.26 08:10", "06.11.26 08:35"):
                assert token in text

    # An operator can install the package alongside other forms, but a subsequent
    # plan must never silently replace a manager's edited company version.
    active = await db.scalar(
        select(DocumentTemplateVersion).where(
            DocumentTemplateVersion.template_id == template.id,
            DocumentTemplateVersion.status == "active",
        )
    )
    old_hash, old_note = active.checksum_sha256, active.change_note
    active.checksum_sha256, active.change_note = "a" * 64, "Исправлена верстка в Manager"
    await db.commit()
    with pytest.raises(BundleError, match="пользовательская версия"):
        await inspect_bundle(db, tenant_id=scope.tenant_id, legal_entity_id=issuer.id, bundle=bundle)
    active.checksum_sha256, active.change_note = old_hash, old_note

    issuer.is_vat_payer = True
    await db.commit()
    with pytest.raises(BundleError, match="налогового режима"):
        await inspect_bundle(db, tenant_id=scope.tenant_id, legal_entity_id=issuer.id, bundle=bundle)
    with pytest.raises(ManagedDocumentConflictError, match="НДС"):
        await ManagedDocumentService.create_draft(
            db,
            tenant_scope=scope,
            template_id=template.id,
            selection=selection,
            template_storage=template_storage,
        )
    # The same seller is still free to use its own waybill with independently configured tax fields.
    custom_draft = await ManagedDocumentService.create_draft(
        db,
        tenant_scope=scope,
        template_id=custom.id,
        selection=selection,
        template_storage=template_storage,
    )
    assert custom_draft.template_version_id
    issuer.is_vat_payer = False
    tenant.slug = "another-synthetic-company"
    await db.commit()
    with pytest.raises(BundleError, match="другого продавца"):
        await apply_bundle(db, scope=scope, legal_entity_id=issuer.id, bundle=bundle, prepared=prepared)


def test_stock_rejects_letter_even_if_the_visible_area_is_cropped_to_a4():
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    page.cropbox.upper_right = (595.28, 841.89)
    content = BytesIO()
    writer.write(content)
    with pytest.raises(ManagedDocumentConflictError, match="A4"):
        validate_stock_pdf(content.getvalue())
