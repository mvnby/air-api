from datetime import date
from io import BytesIO

import asyncio

import pytest
from docx import Document
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select

from models import DocumentNumberReservation, DocumentTemplate, DocumentTemplateVersion, OrderStatus
from models.tenancy import TenantScope
from modules.documents.api.draft_selection import selection_from_payload
from modules.documents.api.managed_documents_artifacts import _document_item_from_parts
from modules.documents.api.schemas import ManagedDocumentDraftPayload
from modules.documents.application import ManagedDocumentService
from modules.documents.application.customer_readiness import check_selection_readiness
from modules.documents.application.draft_mutations import ManagedDocumentDraftMutationService as Mutations
from modules.documents.application.draft_preview import ManagedDocumentDraftPreviewService
from modules.documents.application.errors import (
    ManagedDocumentConflictError, ManagedDocumentGenerationError, ManagedDocumentNotFoundError,
)
from modules.documents.domain.repair_defect import RepairDefect
from modules.documents.infrastructure.renderers.repair_defect_template import TYPE
from tests.integration.test_participant_statement import RecordingPdfConverter, seed

FACTS = dict(equipment="Сплит-система, модель M24, инв. № 7", verdict="repairable",
             finding="Утечка в вальцовочном соединении.", recommendation="Восстановить соединение и заправить систему.")


def selection(order, issuer, **overrides):
    payload = ManagedDocumentDraftPayload(
        legal_entity_id=issuer.id, document_type=TYPE, issue_date=date(2026, 11, 5),
        repair_defect={**FACTS, **overrides},
    )
    return selection_from_payload(order.id, payload)


async def prepare(db, tmp_path):
    scope, order, issuer, templates, artifacts = await seed(db, tmp_path)
    order.workflow_type = "repair"
    order.delivery_address = "г. Витебск, Тестовая 16"
    order.technical_meta = {"repair": {"likely_diagnosis": "Внутренняя гипотеза о компрессоре",
                                        "diagnostic_notes": "Журнал замеров мастера",
                                        "repair_estimate_text": "Предварительные 9999 BYN"}}
    db.add(order)
    await db.commit()
    return scope, order, issuer, templates, artifacts


def document_text(source):
    doc = Document(BytesIO(source))
    return "\n".join([p.text for p in doc.paragraphs] + [cell.text for table in doc.tables for row in table.rows for cell in row.cells])


@pytest.mark.asyncio
async def test_repair_first_use_readiness_issue_and_frozen_client_copy(db, tmp_path):
    scope, order, issuer, templates, artifacts = await prepare(db, tmp_path)
    choice = selection(order, issuer)
    readiness_args = dict(tenant_scope=scope, selection=choice, template_id=None, template_storage=templates)
    readiness = await check_selection_readiness(db, **readiness_args)
    assert readiness == dict(checked=True, missing_fields=[], can_issue=True, template_id=None, template_version_id=None)
    assert await db.scalar(select(func.count()).select_from(DocumentTemplate)) == 0
    assert await db.scalar(select(func.count()).select_from(DocumentNumberReservation)) == 0

    draft = await ManagedDocumentService.create_draft(db, **readiness_args)
    assert draft.official_number is None
    assert draft.render_snapshot["table_rows"] == {}
    assert "totals.amount" not in draft.render_snapshot["values"]
    assert "Внутренняя гипотеза" not in str(draft.render_snapshot)
    assert _document_item_from_parts(draft, []).repair_defect == choice.repair_defect
    readiness = await check_selection_readiness(db, **readiness_args)
    assert readiness["checked"] and readiness["template_version_id"] == draft.template_version_id

    converter = RecordingPdfConverter()
    args = dict(tenant_scope=scope, document_id=draft.id, template_storage=templates,
                artifact_storage=artifacts, pdf_converter=converter)
    await ManagedDocumentDraftPreviewService.render_pdf(db, **args)
    text = document_text(converter.contents[-1])
    assert "НОМЕР НЕ ПРИСВОЕН" in text
    assert FACTS["equipment"] in text and FACTS["finding"] in text
    assert "Оборудование подлежит ремонту" in text and FACTS["recommendation"] in text
    assert text.count("Стоимость и срок ремонта пока не определены.") == 1
    assert "Подлежит уточнению" not in text
    assert "Ограничение эксплуатации" not in text
    assert order.delivery_address in text and "Журнал замеров" not in text and "9999" not in text

    revision = (await Mutations.get(db, tenant_scope=scope, document_id=draft.id))["revision"]
    updated = {**FACTS, "cost": "320 BYN с материалами", "term": "Два рабочих дня после согласования",
               "restriction": "До устранения утечки не включать охлаждение"}
    await Mutations.update(db, tenant_scope=scope, document_id=draft.id, changes={"repair_defect": updated},
                           expected_revision=revision)
    with pytest.raises(ManagedDocumentConflictError, match="другой вкладке"):
        await Mutations.update(db, tenant_scope=scope, document_id=draft.id, changes={"repair_defect": FACTS},
                               expected_revision=revision)
    order.delivery_address = "Другой адрес"
    order.technical_meta = {}
    db.add(order)
    await db.commit()

    class BrokenPdf:
        def convert_docx(self, content, *, filename):
            raise RuntimeError("test converter unavailable")

    with pytest.raises(ManagedDocumentGenerationError):
        await ManagedDocumentService.issue(db, **{**args, "pdf_converter": BrokenPdf()})
    issued = await ManagedDocumentService.issue(db, **args)
    text = document_text(converter.contents[-1])
    assert "ДАР-2026-001" in text and "{{" not in text and "Другой адрес" not in text
    assert "г. Витебск, Тестовая 16" in text
    assert all(updated[k] in text for k in ("equipment", "finding", "recommendation", "restriction", "cost", "term"))
    assert "Подлежит уточнению" not in text
    assert issued.document.status == "issued"
    again = await ManagedDocumentService.issue(db, **args)
    assert {a.id for a in issued.artifacts} == {a.id for a in again.artifacts}
    assert await db.scalar(select(func.count()).select_from(DocumentNumberReservation)) == 1
    with pytest.raises(ManagedDocumentConflictError):
        await Mutations.update(db, tenant_scope=scope, document_id=draft.id, expected_revision=revision,
                               changes={"repair_defect": FACTS})


@pytest.mark.asyncio
async def test_repair_act_order_scoping_and_disabled_or_custom_template(db, tmp_path):
    scope, order, issuer, templates, artifacts = await prepare(db, tmp_path)
    choice = selection(order, issuer)
    kwargs = dict(tenant_scope=scope, selection=choice, template_storage=templates)
    with pytest.raises(ManagedDocumentNotFoundError):
        await ManagedDocumentService.create_draft(db, **{**kwargs, "tenant_scope": TenantScope(tenant_id=999, storefront_id=999)})
    order.workflow_type = "maintenance"
    db.add(order)
    await db.commit()
    with pytest.raises(ManagedDocumentConflictError, match="заказ на ремонт"):
        await ManagedDocumentService.create_draft(db, **kwargs)
    assert await db.scalar(select(func.count()).select_from(DocumentTemplate)) == 0
    order.workflow_type = "repair"
    db.add(order)
    await db.commit()
    draft = await ManagedDocumentService.create_draft(db, **kwargs)
    template = await db.get(DocumentTemplate, draft.document_template_id)
    template.name = "Согласованное клиентское заключение"
    db.add(template)
    await db.commit()
    again = await ManagedDocumentService.create_draft(db, **kwargs)
    assert again.template_version_id == draft.template_version_id

    template.is_active = False
    db.add(template)
    await db.commit()
    with pytest.raises(ManagedDocumentConflictError, match="отключён"):
        await check_selection_readiness(db, template_id=None, **kwargs)
    with pytest.raises(ManagedDocumentConflictError, match="отключён"):
        await ManagedDocumentService.create_draft(db, **kwargs)
    assert await db.scalar(select(func.count()).select_from(DocumentTemplateVersion)) == 1
    await db.rollback()
    order.status = OrderStatus.CLOSED
    db.add(order)
    await db.commit()
    with pytest.raises(ManagedDocumentConflictError, match="завершён"):
        await ManagedDocumentService.issue(db, tenant_scope=scope, document_id=draft.id,
                                          template_storage=templates, artifact_storage=artifacts,
                                          pdf_converter=RecordingPdfConverter())


@pytest.mark.parametrize(("verdict", "label", "show_estimate"), [
    ("repairable", "Оборудование подлежит ремонту", True),
    ("needs_diagnostics", "Для решения о ремонте нужна дополнительная диагностика", True),
    ("uneconomical", "Ремонт экономически нецелесообразен", False),
    ("not_repairable", "Оборудование не подлежит ремонту", False),
    ("operational", "Оборудование исправно", False),
])
def test_explicit_verdict_never_infers_restriction_price_or_writeoff(verdict, label, show_estimate):
    facts = RepairDefect(**{**FACTS, "verdict": verdict})
    snapshot = {"values": {}, "conditions": {}}
    facts.update_snapshot(snapshot)
    assert snapshot["values"]["repair.verdict"] == label
    assert snapshot["conditions"]["repair.has_estimate_note"] is show_estimate
    assert not snapshot["conditions"]["repair.has_cost"]
    assert not snapshot["conditions"]["repair.has_term"]
    assert not snapshot["conditions"]["repair.has_restriction"]
    assert snapshot["values"]["repair.finding"] == FACTS["finding"]


def test_only_repair_payload_accepts_validated_compact_conclusion():
    common = dict(legal_entity_id=1, issue_date=date(2026, 11, 5))
    for overrides in ({"verdict": "repair"}, {"finding": "  \n "}, {"equipment": ""}, {"recommendation": "x" * 321}):
        with pytest.raises(ValidationError):
            ManagedDocumentDraftPayload(**common, document_type=TYPE, repair_defect={**FACTS, **overrides})
    with pytest.raises(ValidationError):
        ManagedDocumentDraftPayload(**common, document_type="act", repair_defect=FACTS)
    with pytest.raises(ValidationError):
        ManagedDocumentDraftPayload(**common, document_type=TYPE)

@pytest.mark.asyncio
async def test_simultaneous_first_drafts_use_one_initial_template(db_engine, tmp_path):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessions() as session:
        scope, order, issuer, templates, _ = await prepare(session, tmp_path)
        choice = selection(order, issuer)

    async def create():
        async with sessions() as session:
            doc = await ManagedDocumentService.create_draft(
                session, tenant_scope=scope, selection=choice, template_storage=templates,
            )
            return doc.id, doc.template_version_id

    first, second = await asyncio.gather(create(), create())
    assert first[0] != second[0] and first[1] == second[1]
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(DocumentTemplateVersion)) == 1
        assert await session.scalar(select(func.count()).select_from(DocumentNumberReservation)) == 0


@pytest.mark.parametrize(("verdict", "cost", "term", "expected_cost", "expected_term"), [
    ("repairable", "300 BYN", None, "300 BYN", "Подлежит уточнению"),
    ("needs_diagnostics", None, "После поставки детали", "Подлежит уточнению", "После поставки детали"),
    ("uneconomical", "1700 BYN по согласованной смете", None, "1700 BYN по согласованной смете", ""),
])
def test_partial_estimate_only_shows_supported_numbers(verdict, cost, term, expected_cost, expected_term):
    facts = RepairDefect(**{**FACTS, "verdict": verdict}, cost=cost, term=term)
    snapshot = {"values": {}, "conditions": {}}
    facts.update_snapshot(snapshot)
    assert snapshot["values"]["repair.cost"] == expected_cost
    assert snapshot["values"]["repair.term"] == expected_term
    assert not snapshot["conditions"]["repair.has_estimate_note"]
    assert snapshot["conditions"]["repair.has_cost"] == bool(expected_cost)
    assert snapshot["conditions"]["repair.has_term"] == bool(expected_term)
