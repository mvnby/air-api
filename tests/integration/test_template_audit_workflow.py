"""Real PostgreSQL receipts, ownership and immutable native-template reviews."""

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO

from docx import Document
from docx.oxml import OxmlElement
from fastapi import HTTPException
import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from models import (
    Customer, DocumentArtifact, DocumentLegalEntity, DocumentTemplate,
    DocumentTemplateAudit, DocumentTemplateAuditProposal, DocumentTemplateCustomerLink,
    DocumentTemplateVersion, OrderDocument, StaffUser, Tenant,
)
from models.command_audit import CommandAuditEvent
from models.tenancy import Storefront, TenantMembership, TenantScope
from api_contracts.document_template_audits import (
    TemplateAuditDecisionInput, TemplateAuditLawSource, TemplateAuditListInput, TemplateAuditProposalInput,
    TemplateAuditReadInput, TemplateAuditSaveInput,
)
from modules.documents.application.template_audit import CHECKLIST, TemplateAuditService
from modules.documents.application.template_audit_commands import TemplateAuditCommands
from modules.documents.application.template_audit_preview import (
    fictional_preview_context, render_proposal_preview,
)
from modules.documents.application.template_versions import (
    NativeTemplatePlaceholderContract, NativeTemplateVersionService,
)
from modules.documents.domain import B2C_NATIVE_DOCUMENT_TYPES
from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
from services.private_attachment_storage_service import LocalPrivateAttachmentStorage
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict


CLAUSE = "Исполнитель обязуется завершить монтаж за 10 рабочих дней."
REPLACEMENT = "Исполнитель обязуется завершить монтаж за 15 рабочих дней."
LONG_PARAGRAPH = " ".join(sha256(str(i).encode()).hexdigest() for i in range(150))


def _docx(*, incomplete=False):
    document = Document()
    document.add_paragraph("Договор № {{ document.official_number }}")
    paragraph = document.add_paragraph(CLAUSE)
    if incomplete:
        paragraph.add_run()._r.append(OxmlElement("w:drawing"))
    document.add_paragraph(LONG_PARAGRAPH)
    document.add_paragraph("{{ #if seller.is_not_vat_payer }}")
    document.add_paragraph("Цена без НДС")
    document.add_paragraph("{{ /if seller.is_not_vat_payer }}")
    document.add_table(rows=1, cols=1).cell(0, 0).text = CLAUSE
    document.sections[0].header.paragraphs[0].text = "Заголовок договора"
    document.sections[0].footer.paragraphs[0].text = "Окончание договора"
    output = BytesIO()
    document.save(output)
    return output.getvalue()


@dataclass
class AuditEnvironment:
    db: AsyncSession
    actor: CommandActor
    membership: TenantMembership
    issuer: DocumentLegalEntity
    template: DocumentTemplate
    version: DocumentTemplateVersion
    customer: Customer
    storage: PrivateTemplateSourceStorage
    source: bytes


async def _seed(db, tmp_path, *, incomplete=False):
    user = StaffUser(username="template-auditor", display_name="Template owner",
                     primary_role="admin", roles=["admin"])
    db.add(user)
    await db.flush()
    membership = TenantMembership(tenant_id=1, staff_user_id=user.id, role="owner")
    issuer = DocumentLegalEntity(tenant_id=1, slug="audit-issuer", display_name="Audit issuer",
                                 requisites={}, is_vat_payer=False)
    customer = Customer(tenant_id=1, name="Synthetic customer", phone="+375290000001")
    db.add_all([membership, issuer, customer])
    await db.commit()
    actor = CommandActor(user.id, user.username, TenantScope(1, 1), "chatgpt")
    template = await NativeTemplateVersionService.create_template(
        db, tenant_scope=actor.tenant_scope, legal_entity_id=issuer.id,
        name="Synthetic contract", doc_type="contract")
    source = _docx(incomplete=incomplete)
    storage = PrivateTemplateSourceStorage(LocalPrivateAttachmentStorage(tmp_path / "private"))
    version = await NativeTemplateVersionService.upload_native_docx_version(
        db, tenant_scope=actor.tenant_scope, legal_entity_id=issuer.id,
        template_id=template.id, filename="contract.docx", content=source,
        placeholder_contract=NativeTemplatePlaceholderContract.create(
            field_catalog={"document.official_number"},
            condition_catalog={"seller.is_not_vat_payer"}, table_blocks=()), storage=storage)
    await NativeTemplateVersionService.activate_version(
        db, tenant_scope=actor.tenant_scope, legal_entity_id=issuer.id,
        template_id=template.id, version_id=version.id)
    return AuditEnvironment(db, actor, membership, issuer, template, version, customer, storage, source)


@pytest.fixture
async def audit_env(db_engine, tmp_path):
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        yield await _seed(db, tmp_path)


async def _read(env, **updates):
    inputs = TemplateAuditReadInput(legal_entity_id=env.issuer.id,
                                   template_id=env.template.id, **updates)
    return await TemplateAuditService.read(env.db, env.actor, inputs, storage=env.storage)


async def _save_input(env, *, key="template-audit-save-0001", customer=False, category="editorial"):
    read = await _read(env, **({"customer_id": env.customer.id} if customer else {}))
    block = next(block for block in read.blocks if block["text"] == CLAUSE)
    checked_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    return TemplateAuditSaveInput(
        legal_entity_id=env.issuer.id, template_id=env.template.id, version_id=env.version.id,
        customer_id=env.customer.id if customer else None,
        source_hash=read.source_hash, context_hash=read.context_hash,
        checked_at=checked_at, review_date=checked_at.date(), idempotency_key=key,
        checklist={item: "checked" for item in CHECKLIST}, findings=[{
            "block_id": block["block_id"], "original_text": "10 рабочих дней",
            "category": category, "risk": "Уточнить согласованный срок",
            "severity": "medium", "proposed_text": "15 рабочих дней", "confidence": "high",
            "verification": "verified", "applicability": "Synthetic contract only", "sources": [],
        }])


async def _saved(env, **kwargs):
    inputs = await _save_input(env, **kwargs)
    return inputs, (await TemplateAuditCommands.save(
        env.db, env.actor, inputs, storage=env.storage))["result"]


def _guard(report):
    return dict(expected_revision=report.revision, source_hash=report.source_hash,
                context_hash=report.context_hash, legal_sources_hash=report.legal_sources_hash)


def _proposal(report, *, key="template-audit-propose-001", **updates):
    finding = report.findings[0]
    data = dict(report_id=report.id, idempotency_key=key, **_guard(report), edits=[{
        "finding_id": finding["id"], "block_id": finding["block_id"],
        "expected_text": CLAUSE, "replacement_text": REPLACEMENT,
        "reason": "Согласовать срок исполнения",
    }])
    data.update(updates)
    return TemplateAuditProposalInput(**data)


async def _count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.mark.asyncio
async def test_read_pages_reconstruct_every_story_and_long_paragraph(audit_env):
    env = audit_env
    page = await _read(env, limit=1)
    first = page
    fragments = []
    while True:
        assert page.coverage["complete"]
        assert page.source_hash == sha256(env.source).hexdigest()
        fragments.extend(page.blocks)
        if not page.next_cursor:
            break
        page = await _read(env, limit=1, cursor=page.next_cursor)
    blocks = {}
    for fragment in fragments:
        prior = blocks.get(fragment["block_id"], "")
        assert fragment["text_offset"] == len(prior)
        blocks[fragment["block_id"]] = prior + fragment["text"]
        if fragment["last_fragment"]:
            assert len(blocks[fragment["block_id"]]) == fragment["text_length"]
    assert list(blocks.values()).count(CLAUSE) == 2
    assert LONG_PARAGRAPH in blocks.values()
    assert {"Заголовок договора", "Окончание договора"} <= set(blocks.values())
    assert sum(f["text_length"] == len(LONG_PARAGRAPH) for f in fragments) == 3
    env.issuer.legal_name = "Changed issuer"
    await env.db.commit()
    with pytest.raises(HTTPException) as error:
        await _read(env, limit=1, cursor=first.next_cursor)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_save_propose_replay_leave_source_active_and_create_no_business_documents(audit_env):
    env = audit_env
    inputs, report = await _saved(env)
    replay = await TemplateAuditCommands.save(env.db, env.actor, inputs, storage=env.storage)
    assert replay["replayed"] and replay["result"].id == report.id
    assert report.checked_at.tzinfo is not None and len(report.checklist) == 8
    assert set(report.checklist) == CHECKLIST
    assert len(report.findings) == 1 and len(report.findings[0]["occurrences"]) == 2
    with pytest.raises(PublicWriteIdempotencyConflict):
        await TemplateAuditCommands.save(env.db, env.actor, inputs.model_copy(update={
            "checklist": {**inputs.checklist, "payment": "unverified"}}), storage=env.storage)
    proposal = _proposal(report)
    changed = await TemplateAuditCommands.propose(env.db, env.actor, proposal, storage=env.storage)
    current = changed["result"]
    assert not changed["replayed"] and not current.stale
    assert current.revision == report.revision + 1
    assert len(current.proposals) == 1
    recorded = current.proposals[0]
    assert recorded["base_version_id"] == env.version.id and recorded["status"] == "draft"
    assert recorded["edits"][0]["expected_text"] == CLAUSE
    assert recorded["edits"][0]["replacement_text"] == REPLACEMENT
    retry = await TemplateAuditCommands.propose(env.db, env.actor, proposal, storage=env.storage)
    assert retry["replayed"] and retry["result"].proposals[0]["id"] == recorded["id"]
    assert retry["result"].proposals[0]["version_id"] == recorded["version_id"]
    changed_retry = proposal.model_copy(deep=True)
    changed_retry.edits[0].reason = "Другой запрос с прежним ключом"
    with pytest.raises(PublicWriteIdempotencyConflict):
        await TemplateAuditCommands.propose(env.db, env.actor, changed_retry, storage=env.storage)
    draft = await _read(env, version_id=recorded["version_id"])
    assert REPLACEMENT in [block["text"] for block in draft.blocks]
    assert (await _read(env)).version["id"] == env.version.id
    await env.db.refresh(env.version)
    assert env.version.status == "active"
    assert await env.storage.read_persisted(tenant_id=1, template_id=env.template.id,
        version=env.version.version, storage_key=env.version.source_storage_key,
        filename=env.version.source_filename, checksum_sha256=env.version.checksum_sha256) == env.source
    assert await _count(env.db, DocumentTemplateVersion) == 2
    assert await _count(env.db, DocumentTemplateAudit) == 1
    assert await _count(env.db, DocumentTemplateAuditProposal) == 1
    assert await _count(env.db, CommandAuditEvent) == 2
    assert await _count(env.db, OrderDocument) == await _count(env.db, DocumentArtifact) == 0


@pytest.mark.asyncio
async def test_proposal_retry_after_commit_acknowledgement_timeout(audit_env, monkeypatch):
    env = audit_env
    _, report = await _saved(env)
    proposal = _proposal(report)
    real_commit = env.db.commit

    async def commit_then_lose_acknowledgement():
        await real_commit()
        raise TimeoutError("Response lost after durable commit")

    with monkeypatch.context() as patch:
        patch.setattr(env.db, "commit", commit_then_lose_acknowledgement)
        with pytest.raises(TimeoutError):
            await TemplateAuditCommands.propose(env.db, env.actor, proposal, storage=env.storage)
    replay = await TemplateAuditCommands.propose(env.db, env.actor, proposal, storage=env.storage)
    assert replay["replayed"] and len(replay["result"].proposals) == 1
    assert await _count(env.db, DocumentTemplateVersion) == 2
    assert await _count(env.db, DocumentTemplateAuditProposal) == 1


@pytest.mark.asyncio
async def test_manager_decision_survives_same_findings_rerun_and_stale_guard(audit_env):
    env = audit_env
    inputs, report = await _saved(env)
    decision = TemplateAuditDecisionInput(**_guard(report), status="rejected", reason="Срок согласован")
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.decide(env.db, env.actor, report.id, report.findings[0]["id"], decision)
    assert error.value.status_code == 403
    manager = replace(env.actor, channel="manager")
    decided = await TemplateAuditCommands.decide(env.db, manager, report.id, report.findings[0]["id"], decision)
    assert decided.findings[0]["status"] == "rejected"
    history = decided.findings[0]["decision_history"]
    assert len(history) == 1 and history[0]["actor"] == env.actor.staff_user_id
    assert history[0]["source_hash"] == report.source_hash and history[0]["channel"] == "manager"
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.decide(env.db, manager, report.id, report.findings[0]["id"], decision)
    assert error.value.status_code == 409
    rerun = await TemplateAuditCommands.save(env.db, env.actor,
        inputs.model_copy(update={"idempotency_key": "template-audit-rerun-0001"}), storage=env.storage)
    assert rerun["result"].id == report.id and len(rerun["result"].findings) == 1
    assert rerun["result"].findings[0]["status"] == "rejected"
    assert rerun["result"].findings[0]["decision_history"] == history
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.propose(env.db, env.actor, _proposal(rerun["result"]), storage=env.storage)
    assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["missing_check", "extra_check", "naive_date", "future_date", "wrong_date", "wrong_block"])
async def test_invalid_or_ungrounded_report_has_no_receipt(audit_env, invalid):
    env = audit_env
    inputs = await _save_input(env)
    if invalid in {"missing_check", "extra_check"}:
        checklist = dict(inputs.checklist)
        if invalid == "missing_check":
            checklist.pop("payment")
        else:
            checklist["invented"] = "checked"
        inputs.checklist = checklist
    elif invalid == "naive_date":
        inputs.checked_at = inputs.checked_at.replace(tzinfo=None)
    elif invalid == "future_date":
        inputs.checked_at += timedelta(days=1)
        inputs.review_date = inputs.checked_at.date()
    elif invalid == "wrong_date":
        inputs.review_date -= timedelta(days=1)
    else:
        inputs.findings[0].original_text = "Отсутствующее условие"
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.save(env.db, env.actor, inputs, storage=env.storage)
    assert error.value.status_code == (409 if invalid == "wrong_block" else 400)
    assert await _count(env.db, DocumentTemplateAudit) == await _count(env.db, CommandAuditEvent) == 0


@pytest.mark.asyncio
async def test_official_tax_source_does_not_certify_missing_issuer_tax_context(audit_env):
    env = audit_env
    inputs = await _save_input(env, category="tax")
    inputs.findings[0].sources = [TemplateAuditLawSource(**{
        "url": "https://pravo.by/document/?guid=synthetic-test", "title": "Synthetic legal edition",
        "provision": "1", "excerpt": "Synthetic excerpt", "checked_at": inputs.checked_at,
        "effective_from": inputs.review_date - timedelta(days=1), "edition": "Synthetic current edition",
        "applicability": "Synthetic test only", "content_hash": "a" * 64,
        "official": True, "verification": "verified",
    })]
    saved = (await TemplateAuditCommands.save(env.db, env.actor, inputs, storage=env.storage))["result"]
    assert saved.findings[0]["verification"] == "unverified"
    assert saved.findings[0]["status"] == "needs_legal_review"
    assert (await _read(env)).context["issuer"]["missing_tax_information"]
    assert saved.legal_currency == "requires_external_recheck"
    confirmed = await TemplateAuditCommands.get(env.db, env.actor, saved.id, saved.legal_sources_hash)
    assert confirmed.legal_currency == "matches_supplied_hash" and not confirmed.stale


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["issuer", "template", "customer", "source", "legal_evidence"])
async def test_changed_context_marks_report_stale_and_refuses_old_proposal(audit_env, changed):
    env = audit_env
    _, report = await _saved(env, customer=True)
    evidence = None
    if changed == "issuer":
        env.issuer.unp = "999999999"
    elif changed == "template":
        env.template.name = "Changed template metadata"
    elif changed == "customer":
        env.customer.acting_basis = "Changed signing basis"
    elif changed == "source":
        env.version.checksum_sha256 = "b" * 64
    else:
        evidence = "c" * 64
    await env.db.commit()
    current = await TemplateAuditCommands.get(env.db, env.actor, report.id, evidence)
    assert current.stale and current.stale_reasons
    if changed == "legal_evidence":
        assert current.legal_currency == "changed"
        proposal = _proposal(report, legal_sources_hash=evidence)
    else:
        proposal = _proposal(report)
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.propose(env.db, env.actor, proposal, storage=env.storage)
    assert error.value.status_code == 409
    assert await _count(env.db, DocumentTemplateAuditProposal) == 0


async def _foreign_records(env):
    db = env.db
    tenant = Tenant(slug="foreign-audit", display_name="Foreign company")
    db.add(tenant)
    await db.flush()
    storefront = Storefront(tenant_id=tenant.id, slug="foreign", display_name="Foreign",
                            is_default=True, status="active")
    issuer = DocumentLegalEntity(tenant_id=tenant.id, slug="foreign", display_name="Foreign issuer")
    customer = Customer(tenant_id=tenant.id, name="Foreign customer", phone="+375290000002")
    db.add_all([storefront, issuer, customer])
    await db.commit()
    scope = TenantScope(tenant.id, storefront.id)
    template = await NativeTemplateVersionService.create_template(db, tenant_scope=scope,
        legal_entity_id=issuer.id, name="Foreign contract", doc_type="contract")
    version = await NativeTemplateVersionService.upload_native_docx_version(db, tenant_scope=scope,
        legal_entity_id=issuer.id, template_id=template.id, filename="foreign.docx", content=env.source,
        placeholder_contract=NativeTemplatePlaceholderContract.create(
            field_catalog={"document.official_number"},
            condition_catalog={"seller.is_not_vat_payer"}, table_blocks=()), storage=env.storage)
    await NativeTemplateVersionService.activate_version(db, tenant_scope=scope,
        legal_entity_id=issuer.id, template_id=template.id, version_id=version.id)
    return issuer, template, customer, version


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["issuer", "template", "customer", "version"])
async def test_foreign_ids_are_invisible_to_source_read_and_report_save(audit_env, resource):
    env = audit_env
    inputs = await _save_input(env)
    issuer, template, customer, version = await _foreign_records(env)
    update = {
        "issuer": {"legal_entity_id": issuer.id}, "template": {"template_id": template.id},
        "customer": {"customer_id": customer.id}, "version": {"version_id": version.id},
    }[resource]
    read = TemplateAuditReadInput(legal_entity_id=env.issuer.id, template_id=env.template.id).model_copy(update=update)
    with pytest.raises(HTTPException) as error:
        await TemplateAuditService.read(env.db, env.actor, read, storage=env.storage)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.save(env.db, env.actor, inputs.model_copy(update=update), storage=env.storage)
    assert error.value.status_code == 404
    assert await _count(env.db, DocumentTemplateAudit) == 0


@pytest.mark.asyncio
async def test_foreign_saved_report_cannot_be_read_or_used_for_proposal(audit_env):
    env = audit_env
    issuer, template, customer, version = await _foreign_records(env)
    storefront = (await env.db.execute(select(Storefront).where(Storefront.tenant_id == issuer.tenant_id))).scalar_one()
    membership = TenantMembership(tenant_id=issuer.tenant_id,
        staff_user_id=env.actor.staff_user_id, role="owner")
    env.db.add(membership)
    await env.db.commit()
    foreign = replace(env, issuer=issuer, template=template, version=version, customer=customer,
        membership=membership, actor=replace(env.actor, tenant_scope=TenantScope(issuer.tenant_id, storefront.id)))
    _, report = await _saved(foreign)
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.get(env.db, env.actor, report.id)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.propose(env.db, env.actor, _proposal(report), storage=env.storage)
    assert error.value.status_code == 404
    assert await _count(env.db, DocumentTemplateAuditProposal) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["role", "membership"])
async def test_live_membership_revocation_denies_saved_snippets_and_mutations(audit_env, revocation):
    env = audit_env
    inputs, report = await _saved(env)
    if revocation == "role":
        env.membership.role = "manager"
    else:
        env.membership.status = "suspended"
    await env.db.commit()
    for operation in (
        lambda: _read(env),
        lambda: TemplateAuditCommands.get(env.db, env.actor, report.id),
        lambda: TemplateAuditCommands.save(env.db, env.actor, inputs, storage=env.storage),
        lambda: TemplateAuditCommands.propose(env.db, env.actor, _proposal(report), storage=env.storage),
    ):
        with pytest.raises(HTTPException) as error:
            await operation()
        assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_customer_restriction_is_enforced_for_lists_reads_and_saved_reports(audit_env):
    env = audit_env
    env.template.client_restricted = True
    env.db.add(DocumentTemplateCustomerLink(template_id=env.template.id, customer_id=env.customer.id))
    await env.db.commit()
    without_customer = await TemplateAuditService.list_templates(env.db, env.actor, TemplateAuditListInput())
    assert without_customer.total == 0
    allowed = await TemplateAuditService.list_templates(env.db, env.actor,
        TemplateAuditListInput(customer_id=env.customer.id))
    assert allowed.total == 1 and allowed.items[0]["id"] == env.template.id
    with pytest.raises(HTTPException) as error:
        await _read(env)
    assert error.value.status_code == 404
    _, report = await _saved(env, customer=True)
    link = (await env.db.execute(select(DocumentTemplateCustomerLink))).scalar_one()
    await env.db.delete(link)
    await env.db.commit()
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.get(env.db, env.actor, report.id)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_incomplete_docx_is_explicit_and_cannot_produce_draft(db_engine, tmp_path):
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        env = await _seed(db, tmp_path, incomplete=True)
        read = await _read(env)
        assert not read.coverage["complete"]
        assert any(reason["code"] == "drawing" for reason in read.coverage["reasons"])
        _, report = await _saved(env)
        with pytest.raises(HTTPException) as error:
            await TemplateAuditCommands.propose(db, env.actor, _proposal(report), storage=env.storage)
        assert error.value.status_code == 409
        assert await _count(db, DocumentTemplateVersion) == 1


@pytest.mark.asyncio
async def test_finding_substring_cannot_replace_only_part_of_source_block(audit_env):
    env = audit_env
    _, report = await _saved(env)
    proposal = _proposal(report)
    proposal.edits[0].expected_text = "10 рабочих дней"
    proposal.edits[0].replacement_text = "15 рабочих дней"
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.propose(env.db, env.actor, proposal, storage=env.storage)
    assert error.value.status_code == 409
    assert await _count(env.db, DocumentTemplateAuditProposal) == 0
    assert await _count(env.db, DocumentTemplateVersion) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["expected_revision", "source_hash", "context_hash", "legal_sources_hash"])
async def test_manager_decisions_require_exact_revision_and_all_evidence_hashes(audit_env, changed):
    env = audit_env
    _, report = await _saved(env)
    guard = _guard(report)
    guard[changed] = report.revision + 1 if changed == "expected_revision" else "d" * 64
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.decide(env.db, replace(env.actor, channel="manager"),
            report.id, report.findings[0]["id"], TemplateAuditDecisionInput(
                **guard, status="accepted", reason="Explicit test decision"))
    assert error.value.status_code == 409
    current = await TemplateAuditCommands.get(env.db, env.actor, report.id)
    assert current.revision == report.revision and current.findings[0]["decision_history"] == []


@pytest.mark.asyncio
async def test_missing_private_source_is_visible_and_cannot_save_or_propose(audit_env):
    env = audit_env
    inputs, report = await _saved(env)
    env.version.source_storage_key = (
        f"missing/document-templates-tenant-1-template-{env.template.id}-version-{env.version.version}.docx")
    await env.db.commit()
    read = await _read(env)
    assert not read.coverage["complete"] and read.source_hash is None and read.blocks == []
    assert read.source_download_url is None
    assert read.coverage["reasons"][0]["code"] == "source_unavailable_or_invalid"
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.save(env.db, env.actor, inputs.model_copy(update={
            "idempotency_key": "template-audit-unavailable-source"}), storage=env.storage)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.propose(env.db, env.actor, _proposal(report), storage=env.storage)
    assert error.value.status_code == 409
    assert await _count(env.db, DocumentTemplateAuditProposal) == 0


@pytest.mark.asyncio
async def test_fictional_native_preview_renders_conditions_without_creating_documents(audit_env):
    env = audit_env
    _, report = await _saved(env)
    current = (await TemplateAuditCommands.propose(
        env.db, env.actor, _proposal(report), storage=env.storage))["result"]
    proposal_id = current.proposals[0]["id"]
    fictional = await fictional_preview_context(env.db, env.actor, report.id, proposal_id, storage=env.storage)
    assert fictional.synthetic and "вымышленные" in fictional.label
    assert fictional.values == {"document.official_number": "ТЕСТ-001"}
    assert fictional.conditions == {"seller.is_not_vat_payer": True}
    docx = await render_proposal_preview(env.db, env.actor, report.id, proposal_id,
        fictional.model_copy(update={"format": "docx"}), pdf_converter=None, storage=env.storage)
    rendered = Document(BytesIO(docx))
    text = "\n".join(paragraph.text for paragraph in rendered.paragraphs)
    assert "Договор № ТЕСТ-001" in text and REPLACEMENT in text and "Цена без НДС" in text
    assert "{{" not in text
    assert (await _read(env)).version["id"] == env.version.id
    assert await _count(env.db, OrderDocument) == await _count(env.db, DocumentArtifact) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["source_hash", "context_hash", "legal_sources_hash", "values", "conditions"])
async def test_preview_rejects_stale_hashes_or_unspecified_fictional_branches(audit_env, invalid):
    env = audit_env
    _, report = await _saved(env)
    current = (await TemplateAuditCommands.propose(
        env.db, env.actor, _proposal(report), storage=env.storage))["result"]
    proposal_id = current.proposals[0]["id"]
    fictional = await fictional_preview_context(env.db, env.actor, report.id, proposal_id, storage=env.storage)
    fictional = fictional.model_copy(update={invalid: {} if invalid in {"values", "conditions"} else "e" * 64,
                                             "format": "docx"})
    with pytest.raises(HTTPException) as error:
        await render_proposal_preview(env.db, env.actor, report.id, proposal_id,
            fictional, pdf_converter=None, storage=env.storage)
    assert error.value.status_code == (400 if invalid in {"values", "conditions"} else 409)
    assert await _count(env.db, OrderDocument) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("stale", [False, True])
async def test_proposal_activation_is_separate_and_refuses_changed_issuer(audit_env, stale):
    env = audit_env
    _, report = await _saved(env)
    current = (await TemplateAuditCommands.propose(
        env.db, env.actor, _proposal(report), storage=env.storage))["result"]
    draft_id = current.proposals[0]["version_id"]
    draft = await env.db.get(DocumentTemplateVersion, draft_id)
    assert draft.status == "draft" and (await _read(env)).version["id"] == env.version.id
    if stale:
        env.issuer.unp = "888888888"
        await env.db.commit()
        with pytest.raises(HTTPException) as error:
            await NativeTemplateVersionService.activate_version(env.db, tenant_scope=env.actor.tenant_scope,
                legal_entity_id=env.issuer.id, template_id=env.template.id, version_id=draft_id,
                expected_active_version_id=env.version.id)
        assert error.value.status_code == 409
        await env.db.refresh(draft)
        assert draft.status == "draft"
        assert (await _read(env)).version["id"] == env.version.id
    else:
        active = await NativeTemplateVersionService.activate_version(env.db, tenant_scope=env.actor.tenant_scope,
            legal_entity_id=env.issuer.id, template_id=env.template.id, version_id=draft_id,
            expected_active_version_id=env.version.id)
        assert active.status == "active" and (await _read(env)).version["id"] == draft_id
        await env.db.refresh(env.version)
        assert env.version.status == "retired"
        with pytest.raises(HTTPException) as error:
            await _read(env, version_id=env.version.id)
        assert error.value.status_code == 409
        archived = await _read(env, version_id=env.version.id, include_archived=True)
        assert archived.version["status"] == "retired" and CLAUSE in [block["text"] for block in archived.blocks]


@pytest.mark.asyncio
@pytest.mark.parametrize("same_key", [False, True])
async def test_concurrent_proposals_serialize_report_revision_and_retry_receipt(audit_env, db_engine, same_key):
    env = audit_env
    _, report = await _saved(env)
    await env.db.rollback()  # Release the read transaction before independent connections.
    first = _proposal(report, key="template-audit-concurrent-01")
    second = _proposal(report, key=first.idempotency_key if same_key else "template-audit-concurrent-02")

    async def propose(inputs):
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            return await TemplateAuditCommands.propose(session, env.actor, inputs, storage=env.storage)

    results = await asyncio.gather(propose(first), propose(second), return_exceptions=True)
    successes = [result for result in results if isinstance(result, dict)]
    if same_key:
        assert len(successes) == 2, results
        assert sorted(result["replayed"] for result in successes) == [False, True]
        assert successes[0]["result"].proposals[0]["id"] == successes[1]["result"].proposals[0]["id"]
    else:
        assert len(successes) == 1, results
        conflict = next(result for result in results if isinstance(result, Exception))
        assert isinstance(conflict, HTTPException) and conflict.status_code == 409
    assert await _count(env.db, DocumentTemplateAuditProposal) == 1
    assert await _count(env.db, DocumentTemplateVersion) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["template", "customer", "source", "legal_evidence"])
async def test_activation_refreshes_cached_guard_rows_after_external_commit(audit_env, db_engine, changed):
    env = audit_env
    _, report = await _saved(env, customer=True)
    current = (await TemplateAuditCommands.propose(
        env.db, env.actor, _proposal(report), storage=env.storage))["result"]
    draft = await env.db.get(DocumentTemplateVersion, current.proposals[0]["version_id"])
    cached_report = await env.db.get(DocumentTemplateAudit, report.id)
    await env.db.commit()
    model, row_id, changes = {
        "template": (DocumentTemplate, env.template.id, {"name": "Concurrent template edit"}),
        "customer": (Customer, env.customer.id, {"signer_name": "Concurrent customer edit"}),
        "source": (DocumentTemplateVersion, draft.id, {"checksum_sha256": "f" * 64}),
        "legal_evidence": (DocumentTemplateAudit, report.id, {"legal_sources_hash": "f" * 64}),
    }[changed]
    async with AsyncSession(db_engine) as writer:
        await writer.execute(update(model).where(model.id == row_id).values(**changes))
        await writer.commit()
    # Keep strong references so the identity map cannot discard the old facts.
    assert draft.status == "draft" and cached_report.legal_sources_hash == report.legal_sources_hash
    with pytest.raises(HTTPException) as error:
        await NativeTemplateVersionService.activate_version(env.db, tenant_scope=env.actor.tenant_scope,
            legal_entity_id=env.issuer.id, template_id=env.template.id, version_id=draft.id,
            expected_active_version_id=env.version.id)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_report_refreshes_cached_customer_after_external_profile_change(audit_env, db_engine):
    env = audit_env
    _, report = await _saved(env, customer=True)
    await env.db.commit()
    async with AsyncSession(db_engine) as writer:
        await writer.execute(update(Customer).where(Customer.id == env.customer.id).values(
            signer_name="Externally changed customer signer"))
        await writer.commit()
    current = await TemplateAuditCommands.get(env.db, env.actor, report.id)
    assert current.stale and "issuer_template_or_customer_context_changed" in current.stale_reasons
    with pytest.raises(HTTPException) as error:
        await TemplateAuditCommands.propose(env.db, env.actor, _proposal(report), storage=env.storage)
    assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["save", "propose"])
@pytest.mark.parametrize("changed", ["restrict_without_customer", "unlink_customer", "disable_issuer", "move_issuer"])
async def test_queued_writer_rechecks_scope_after_template_mutex_wait(
    audit_env, db_engine, monkeypatch, operation, changed,
):
    env = audit_env
    customer_selected = changed == "unlink_customer"
    if customer_selected:
        env.template.client_restricted = True
        env.db.add(DocumentTemplateCustomerLink(template_id=env.template.id, customer_id=env.customer.id))
    replacement_issuer = DocumentLegalEntity(tenant_id=1, slug="replacement-audit-issuer",
                                             display_name="Replacement issuer")
    env.db.add(replacement_issuer)
    await env.db.commit()
    if operation == "save":
        inputs = await _save_input(env, customer=customer_selected)
    else:
        _, report = await _saved(env, customer=customer_selected)
        inputs = _proposal(report)
    await env.db.commit()
    reached_mutex = asyncio.Event()
    original_lock = NativeTemplateVersionService._lock_template

    async def observed_lock(session, tenant_id, template_id):
        if session is env.db:
            reached_mutex.set()
        await original_lock(session, tenant_id, template_id)

    async with AsyncSession(db_engine, expire_on_commit=False) as holder:
        await original_lock(holder, env.actor.tenant_scope.tenant_id, env.template.id)
        await holder.execute(text("SET LOCAL lock_timeout = '2s'"))
        with monkeypatch.context() as patch:
            patch.setattr(NativeTemplateVersionService, "_lock_template", staticmethod(observed_lock))
            command = TemplateAuditCommands.save if operation == "save" else TemplateAuditCommands.propose
            pending = asyncio.create_task(command(env.db, env.actor, inputs, storage=env.storage))
            try:
                await asyncio.wait_for(reached_mutex.wait(), timeout=5)
                assert not pending.done(), "The command must wait for the held PostgreSQL template mutex"
                if changed == "restrict_without_customer":
                    await holder.execute(update(DocumentTemplate).where(DocumentTemplate.id == env.template.id)
                        .values(client_restricted=True))
                elif changed == "unlink_customer":
                    await holder.execute(delete(DocumentTemplateCustomerLink).where(
                        DocumentTemplateCustomerLink.template_id == env.template.id,
                        DocumentTemplateCustomerLink.customer_id == env.customer.id))
                elif changed == "disable_issuer":
                    await holder.execute(update(DocumentLegalEntity).where(DocumentLegalEntity.id == env.issuer.id)
                        .values(status="disabled"))
                else:
                    await holder.execute(update(DocumentTemplate).where(DocumentTemplate.id == env.template.id)
                        .values(legal_entity_id=replacement_issuer.id))
                await holder.commit()
                with pytest.raises(HTTPException) as error:
                    await asyncio.wait_for(pending, timeout=5)
                assert error.value.status_code in {404, 409}
            finally:
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
    assert await _count(env.db, DocumentTemplateAudit) == (1 if operation == "propose" else 0)
    assert await _count(env.db, DocumentTemplateAuditProposal) == 0
    assert await _count(env.db, DocumentTemplateVersion) == 1
    assert await _count(env.db, CommandAuditEvent) == (1 if operation == "propose" else 0)


@pytest.mark.parametrize("document_type", sorted(B2C_NATIVE_DOCUMENT_TYPES))
def test_actual_b2c_template_catalog_projects_consumer_audience(document_type):
    issuer = DocumentLegalEntity(id=1, tenant_id=1, slug="b2c-audit", display_name="Synthetic issuer")
    template = DocumentTemplate(id=1, tenant_id=1, legal_entity_id=1,
                                name="Synthetic B2C template", doc_type=document_type)
    context, _ = TemplateAuditService.context(issuer, template, None, [], [])
    assert context["applicability"]["audience"] == "B2C"
