"""Exercise scoped standard acts through Manager and the native issuance lifecycle."""

import asyncio
from datetime import datetime
from io import BytesIO
from uuid import uuid4

from docx import Document
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select

from core.command_actor import CommandActor
from core.config import settings
from models import OrderDocument, OrderServiceLink, StaffUser, TenantMembership
from models.order_site import OrderSite
from models.tenancy import TenantScope
from modules.documents.application.draft_parameters import draft_revision
from modules.documents.application.errors import ManagedDocumentConflictError
from modules.documents.application.lifecycle_service import ManagedDocumentService
from modules.documents.application.native_template_discovery import discover_native_placeholder_contract
from modules.documents.application.order_completion_acts import OrderCompletionActService
from modules.documents.application.order_completion_coverage import COVERAGE_KEY
from modules.documents.application.template_versions import NativeTemplateVersionService
from modules.documents.infrastructure.artifact_storage import PrivateDocumentArtifactStorage
from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
from schemas_order_completion_acts import OrderCompletionActSourceInput, PrepareOrderCompletionActInput
from services.document_service import DocumentService
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from tests.integration.test_document_context_builder import _seed_order
from tests.integration.test_managed_document_lifecycle import FakePdfConverter
from tests.integration.test_manager_access_permissions import _headers


SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True)


async def seed_completion(db, private):
    order, issuer, proposal, _alternative = await _seed_order(db)
    user = StaffUser(username="completion-test-manager", display_name="Manager", primary_role="manager", roles=["manager"])
    db.add(user)
    await db.flush()
    db.add(TenantMembership(tenant_id=1, staff_user_id=user.id, role="manager"))
    sites = [
        OrderSite(order_id=order.id, customer_id=order.customer_id, title=f"Объект {letter}", address=f"Тестовый адрес {letter}")
        for letter in "ABC"
    ]
    db.add_all(sites)
    await db.commit()
    contract = await DocumentService.register_external_contract(
        db, order_id=order.id, number="ДОГ-123", contract_date=datetime(2026, 11, 1), tenant_scope=SCOPE,
    )
    template_storage = PrivateTemplateSourceStorage(private)
    template = await NativeTemplateVersionService.create_template(
        db, tenant_scope=SCOPE, legal_entity_id=issuer.id, name="Общий акт", doc_type="act",
    )
    doc = Document()
    doc.add_paragraph("Акт № {{ document.official_full_number }}")
    doc.add_paragraph("Объекты: {{ order.object_address }}")
    doc.add_paragraph("Договор № {{ basis.number }}")
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "{{ lines }}{{ line.title }} {{ line.quantity }} {{ line.amount }}"
    output = BytesIO()
    doc.save(output)
    source = output.getvalue()
    version = await NativeTemplateVersionService.upload_native_docx_version(
        db, tenant_scope=SCOPE, legal_entity_id=issuer.id, template_id=template.id, filename="completion-test.docx",
        content=source, placeholder_contract=discover_native_placeholder_contract(source), storage=template_storage,
    )
    await NativeTemplateVersionService.activate_version(
        db, tenant_scope=SCOPE, legal_entity_id=issuer.id, template_id=template.id, version_id=version.id,
    )
    return order, issuer, proposal, contract, sites, template_storage, _headers(user)


@pytest.mark.asyncio
async def test_scoped_completion_prints_all_sites_and_refuses_second_issue(async_client, db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SERVICE_ATTACHMENT_LOCAL_DIR", str(tmp_path))
    private = LocalPrivateAttachmentStorage(tmp_path)
    order, issuer, proposal, contract, sites, template_storage, headers = await seed_completion(db, private)
    path = f"/api/manager/orders/{order.id}/completion-acts"
    source = await async_client.get(path + "/source", headers=headers, params={"proposal_id": proposal.id})
    assert source.status_code == 200, source.text
    command = {
        "idempotency_key": str(uuid4()), "site_ids": [row.id for row in sites], "proposal_id": proposal.id,
        "expected_proposal_version": source.json()["proposal_version"], "legal_entity_id": issuer.id,
        "base_document_id": contract.id, "issue_date": "2026-11-20", "issue_city": "Витебск",
        "document_role_type": "executor_customer", "act_terms": {"claims_status": "none"},
    }
    stale = await async_client.post(path, headers=headers, json={**command, "expected_proposal_version": "0" * 64})
    assert stale.status_code == 409
    prepared = await async_client.post(path, headers=headers, json=command)
    assert prepared.status_code == 200, prepared.text
    draft_id = prepared.json()["result"]["document_id"]
    replay = await async_client.post(path, headers=headers, json=command)
    assert replay.json()["replayed"] and replay.json()["result"]["document_id"] == draft_id
    duplicate = await async_client.post(path, headers=headers, json={**command, "idempotency_key": str(uuid4())})
    assert duplicate.status_code == 200, duplicate.text
    duplicate_id = duplicate.json()["result"]["document_id"]
    draft = await db.get(OrderDocument, draft_id)
    assert draft.base_document_id == contract.id and draft.proposal_id == proposal.id
    rows = draft.render_snapshot["table_rows"]["lines"]
    assert len(rows) == 1 and rows[0]["line.quantity"] == "2"
    assert draft.scope_meta["site_ids"] == command["site_ids"]
    assert "Витебск" == draft.render_snapshot["values"]["document.issue_city"]
    assert [row["address"] for row in draft.render_snapshot["meta"][COVERAGE_KEY]["sites"]] == [
        row.address for row in sites
    ]

    artifact_storage = PrivateDocumentArtifactStorage(private)
    issue_args = dict(tenant_scope=SCOPE, template_storage=template_storage, artifact_storage=artifact_storage,
                      pdf_converter=FakePdfConverter())
    issued = await ManagedDocumentService.issue(db, document_id=draft_id, **issue_args)
    saved = next(item for item in issued.artifacts if item.kind == "rendered_docx")
    doc = Document(BytesIO(await artifact_storage.read(ManagedDocumentService.stored_artifact(saved))))
    object_paragraph = next(item.text for item in doc.paragraphs if item.text.startswith("Объекты:"))
    assert all(row.address in object_paragraph for row in sites)
    assert any(contract.number in paragraph.text for paragraph in doc.paragraphs)
    with pytest.raises(ManagedDocumentConflictError, match="количество или сумму"):
        await ManagedDocumentService.issue(db, document_id=duplicate_id, **issue_args)
    duplicate_draft = await db.get(OrderDocument, duplicate_id)
    assert duplicate_draft.official_number is None



@pytest.mark.asyncio
async def test_partial_act_reservations_are_serialized_with_concurrent_issuers(db_engine, tmp_path):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    private = LocalPrivateAttachmentStorage(tmp_path)
    async with sessions() as session:
        order, issuer, proposal, contract, sites, templates, _headers_value = await seed_completion(session, private)
        user = await session.scalar(select(StaffUser).where(StaffUser.username == "completion-test-manager"))
        actor = CommandActor(user.id, user.username, SCOPE)
        line = await session.scalar(select(OrderServiceLink).where(OrderServiceLink.proposal_id == proposal.id))
        source = await OrderCompletionActService.source(
            session, actor, OrderCompletionActSourceInput(order_id=order.id, proposal_id=proposal.id),
        )
        base = dict(
            order_id=order.id, proposal_id=proposal.id, site_ids=[sites[0].id], legal_entity_id=issuer.id,
            base_document_id=contract.id, expected_proposal_version=source.proposal_version,
            issue_date="2026-11-20", act_terms={"claims_status": "none"},
            scope_service_line_ids=[line.id], scope_service_line_quantities={line.id: 1},
        )
        drafts = []
        for _ in range(3):
            result = await OrderCompletionActService.prepare(
                session, actor, PrepareOrderCompletionActInput(**base, idempotency_key=str(uuid4())),
                template_storage=templates,
            )
            drafts.append(result.value.document_id)

    artifact_storage = PrivateDocumentArtifactStorage(private)

    async def issue_one(document_id):
        async with sessions() as session:
            await ManagedDocumentService.issue(
                session, tenant_scope=SCOPE, document_id=document_id,
                template_storage=templates, artifact_storage=artifact_storage, pdf_converter=FakePdfConverter(),
            )

    outcomes = await asyncio.gather(*(issue_one(document_id) for document_id in drafts), return_exceptions=True)
    assert outcomes.count(None) == 2
    (conflict,) = [error for error in outcomes if error is not None]
    assert isinstance(conflict, ManagedDocumentConflictError) and "количество или сумму" in str(conflict)

    async with sessions() as session:
        issued_id = drafts[outcomes.index(None)]
        old = await ManagedDocumentService.get_document(session, tenant_scope=SCOPE, document_id=issued_id)
        artifacts = await ManagedDocumentService.list_artifacts(session, tenant_scope=SCOPE, document_id=issued_id)
        data = PrepareOrderCompletionActInput(
            **base, idempotency_key=str(uuid4()), replaces_document_id=old.id,
            expected_document_revision=draft_revision(old, artifacts),
        )
        replacement = await OrderCompletionActService.prepare(session, actor, data, template_storage=templates)
    await issue_one(replacement.value.document_id)
    async with sessions() as session:
        old = await session.get(OrderDocument, issued_id)
        updated = await session.get(OrderDocument, replacement.value.document_id)
        rejected = await session.get(OrderDocument, drafts[outcomes.index(conflict)])
        assert old.status == "replaced" and updated.status == "issued"
        assert rejected.status == "draft" and rejected.official_number is None
