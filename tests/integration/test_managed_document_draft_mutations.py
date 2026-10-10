from copy import deepcopy
from dataclasses import replace
from datetime import date
from io import BytesIO

import pytest
from docx import Document
from sqlmodel import select

from models import (
    Customer,
    DocumentArtifact,
    DocumentExternalEditSession,
    DocumentTemplate,
    OrderDocument,
    OrderStatus,
)
from modules.documents.application.draft_mutations import (
    ManagedDocumentDraftMutationService as Drafts,
)
from modules.documents.application.errors import (
    ManagedDocumentConflictError,
    ManagedDocumentNotFoundError,
)
from modules.documents.application.lifecycle_service import ManagedDocumentService
from modules.documents.application.managed_document_external_edits import (
    ManagedDocumentExternalEditSessionService as Editor,
)
from modules.documents.application.template_versions import (
    NativeTemplatePlaceholderContract,
    NativeTemplateVersionService,
)
from modules.documents.infrastructure.renderers import TableBlockSpec
from tests.integration.test_managed_document_lifecycle import (
    FakePdfConverter,
    _draft,
    _seed,
    _template_docx,
)
from tests.integration.test_managed_document_google_editing import (
    FakeGoogleEditor,
    _document_text,
)


@pytest.mark.asyncio
async def test_date_change_keeps_same_draft_and_google_edits_and_uses_new_numbering_year(
    db, tmp_path
):
    scope, order, issuer, templates, artifacts = await _seed(db, tmp_path)
    template = await db.scalar(
        select(DocumentTemplate).where(DocumentTemplate.legal_entity_id == issuer.id)
    )
    dated_source = Document(BytesIO(_template_docx()))
    dated_source.add_paragraph("Дата: {{ document.issued_on }}")
    output = BytesIO()
    dated_source.save(output)
    version = await NativeTemplateVersionService.upload_native_docx_version(
        db,
        tenant_scope=scope,
        legal_entity_id=issuer.id,
        template_id=template.id,
        filename="Договор с датой.docx",
        content=output.getvalue(),
        placeholder_contract=NativeTemplatePlaceholderContract.create(
            field_catalog={
                "document.official_full_number",
                "customer.full_name",
                "document.issued_on",
            },
            table_blocks=(
                TableBlockSpec(
                    name="lines",
                    row_fields=frozenset(
                        {"line.number", "line.title", "line.quantity", "line.amount"}
                    ),
                ),
            ),
        ),
        storage=templates,
    )
    await NativeTemplateVersionService.activate_version(
        db,
        tenant_scope=scope,
        legal_entity_id=issuer.id,
        template_id=template.id,
        version_id=version.id,
    )
    draft = await _draft(
        db, scope=scope, order=order, issuer=issuer, issue_date=date(2026, 10, 9)
    )
    document_id, reference = draft.id, draft.internal_reference
    provider = FakeGoogleEditor()
    editor = await Editor.ensure_session(
        db,
        tenant_scope=scope,
        document_id=document_id,
        template_storage=templates,
        artifact_storage=artifacts,
        provider=provider,
    )
    provider.add_manual_paragraph("Согласовано вручную")
    editor = await Editor.sync(
        db,
        tenant_scope=scope,
        document_id=document_id,
        expected_base_checksum_sha256=editor.base_checksum_sha256,
        expected_remote_revision=provider.revision,
        idempotency_key="draft-date",
        artifact_storage=artifacts,
        provider=provider,
    )
    editor_id = editor.id
    parameters = await Drafts.get(db, tenant_scope=scope, document_id=document_id)
    original_values = deepcopy(draft.render_snapshot["values"])
    # A current customer change must not silently alter the saved draft when changing its date.
    customer = await db.get(Customer, order.customer_id)
    customer.name = "Новая карточка клиента"
    await db.commit()
    changed = await Drafts.update(
        db,
        tenant_scope=scope,
        document_id=document_id,
        expected_revision=parameters["revision"],
        changes={"issue_date": "2025-10-01"},
    )
    assert changed.id == document_id and changed.internal_reference == reference
    assert changed.date.date() == date(2025, 10, 1)
    assert changed.official_number is None
    assert (
        changed.render_snapshot["values"]["customer.full_name"]
        == original_values["customer.full_name"]
    )
    assert changed.render_snapshot["values"]["document.issued_on"] == "01.10.2025"
    assert await db.get(DocumentExternalEditSession, editor_id) is not None
    result = await ManagedDocumentService.issue(
        db,
        tenant_scope=scope,
        document_id=document_id,
        template_storage=templates,
        artifact_storage=artifacts,
        pdf_converter=FakePdfConverter(),
        verified_remote_revision=provider.revision,
    )
    assert result.document.official_date == date(2025, 10, 1)
    assert result.document.official_period_key == "2025"
    rendered = next(item for item in result.artifacts if item.kind == "rendered_docx")
    text = _document_text(
        await artifacts.read(ManagedDocumentService.stored_artifact(rendered))
    )
    assert "Согласовано вручную" in text and "Д-2025-001" in text
    assert "Дата: 01.10.2025" in text
    with pytest.raises(ManagedDocumentConflictError):
        await Drafts.get(db, tenant_scope=scope, document_id=document_id)
    with pytest.raises(ManagedDocumentConflictError):
        await Drafts.update(
            db,
            tenant_scope=scope,
            document_id=document_id,
            expected_revision=parameters["revision"],
            changes={"issue_date": "2025-10-02"},
        )
    with pytest.raises(ManagedDocumentConflictError):
        await Drafts.delete(db, tenant_scope=scope, document_id=document_id)


@pytest.mark.asyncio
async def test_terms_reset_requires_confirmation_and_new_editor_copy_uses_saved_values(
    db, tmp_path
):
    scope, order, issuer, templates, artifacts = await _seed(db, tmp_path)
    draft = await _draft(db, scope=scope, order=order, issuer=issuer)
    document_id = draft.id
    provider = FakeGoogleEditor()
    editor = await Editor.ensure_session(
        db,
        tenant_scope=scope,
        document_id=document_id,
        template_storage=templates,
        artifact_storage=artifacts,
        provider=provider,
    )
    editor_id = editor.id
    parameters = await Drafts.get(db, tenant_scope=scope, document_id=document_id)
    business = {
        **parameters["business_terms"],
        "subject": "Исправленный предмет договора",
        "delivery_deadline": "2026-10-15",
    }
    with pytest.raises(ManagedDocumentConflictError, match="Подтвердите"):
        await Drafts.update(
            db,
            tenant_scope=scope,
            document_id=document_id,
            expected_revision=parameters["revision"],
            changes={"business_terms": business},
        )
    changed = await Drafts.update(
        db,
        tenant_scope=scope,
        document_id=document_id,
        expected_revision=parameters["revision"],
        changes={"business_terms": business, "issue_city": "Минск"},
        reset_editable_copy=True,
    )
    assert changed.id == document_id and changed.official_number is None
    assert changed.render_snapshot["values"]["contract.subject"] == business["subject"]
    assert (
        changed.render_snapshot["values"]["contract.delivery_deadline"] == "15.10.2026"
    )
    assert changed.render_snapshot["values"]["document.issue_city"] == "Минск"
    assert await db.get(DocumentExternalEditSession, editor_id) is None
    assert not await ManagedDocumentService.list_artifacts(
        db, tenant_scope=scope, document_id=document_id
    )
    new_provider = FakeGoogleEditor()
    new_editor = await Editor.ensure_session(
        db,
        tenant_scope=scope,
        document_id=document_id,
        template_storage=templates,
        artifact_storage=artifacts,
        provider=new_provider,
    )
    assert new_editor.id != editor_id


@pytest.mark.asyncio
async def test_delete_draft_removes_all_source_versions_and_editor_sessions(
    db, tmp_path
):
    scope, order, issuer, templates, artifacts = await _seed(db, tmp_path)
    draft = await _draft(db, scope=scope, order=order, issuer=issuer)
    document_id = draft.id
    provider = FakeGoogleEditor()
    editor = await Editor.ensure_session(
        db,
        tenant_scope=scope,
        document_id=document_id,
        template_storage=templates,
        artifact_storage=artifacts,
        provider=provider,
    )
    editor_id = editor.id
    provider.add_manual_paragraph("Ненужный договор")
    await Editor.sync(
        db,
        tenant_scope=scope,
        document_id=document_id,
        expected_base_checksum_sha256=editor.base_checksum_sha256,
        expected_remote_revision=provider.revision,
        idempotency_key="discard-draft",
        artifact_storage=artifacts,
        provider=provider,
    )
    assert (
        len(
            (
                await db.execute(
                    select(DocumentArtifact).where(
                        DocumentArtifact.order_document_id == document_id
                    )
                )
            )
            .scalars()
            .all()
        )
        == 2
    )
    await ManagedDocumentService.delete_draft(
        db, tenant_scope=scope, document_id=document_id
    )
    assert await db.get(OrderDocument, document_id) is None
    assert await db.get(DocumentExternalEditSession, editor_id) is None
    assert (
        not (
            await db.execute(
                select(DocumentArtifact).where(
                    DocumentArtifact.order_document_id == document_id
                )
            )
        )
        .scalars()
        .all()
    )


@pytest.mark.asyncio
async def test_stale_scope_closed_order_and_reserved_number_block_draft_mutations(
    db, tmp_path
):
    scope, order, issuer, _, _ = await _seed(db, tmp_path)
    draft = await _draft(db, scope=scope, order=order, issuer=issuer)
    document_id = draft.id
    parameters = await Drafts.get(db, tenant_scope=scope, document_id=document_id)
    await Drafts.update(
        db,
        tenant_scope=scope,
        document_id=document_id,
        expected_revision=parameters["revision"],
        changes={"issue_date": "2026-10-01"},
    )
    with pytest.raises(ManagedDocumentConflictError, match="другой вкладке"):
        await Drafts.update(
            db,
            tenant_scope=scope,
            document_id=document_id,
            expected_revision=parameters["revision"],
            changes={"issue_date": "2026-10-02"},
        )
    with pytest.raises(ManagedDocumentNotFoundError):
        await Drafts.get(
            db,
            tenant_scope=replace(scope, storefront_id=scope.storefront_id + 1),
            document_id=document_id,
        )
    with pytest.raises(ManagedDocumentNotFoundError):
        await Drafts.delete(
            db,
            tenant_scope=replace(scope, tenant_id=scope.tenant_id + 1),
            document_id=document_id,
        )
    current = await Drafts.get(db, tenant_scope=scope, document_id=document_id)
    order.status = OrderStatus.CLOSED
    await db.commit()
    with pytest.raises(ManagedDocumentConflictError):
        await Drafts.update(
            db,
            tenant_scope=scope,
            document_id=document_id,
            expected_revision=current["revision"],
            changes={"issue_date": "2026-10-02"},
        )
    with pytest.raises(ManagedDocumentConflictError):
        await Drafts.delete(db, tenant_scope=scope, document_id=document_id)
    order.status = OrderStatus.NEGOTIATION
    draft.official_number = "001"
    draft.official_series = "Д"
    draft.official_period_key = "2026"
    draft.official_date = date(2026, 10, 1)
    await db.commit()
    with pytest.raises(ManagedDocumentConflictError, match="официального номера"):
        await Drafts.update(
            db,
            tenant_scope=scope,
            document_id=document_id,
            expected_revision=current["revision"],
            changes={"issue_date": "2026-10-02"},
        )
    with pytest.raises(ManagedDocumentConflictError, match="официального номера"):
        await Drafts.delete(db, tenant_scope=scope, document_id=document_id)
