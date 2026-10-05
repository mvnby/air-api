from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zipfile import ZipFile

import pytest

from models import Customer, CustomerBranch, LeadSource, Order, OrderStatus
from models.tenancy import TenantScope
from schemas_belzakupki_enrichment import ManagerOrderSourceAnalyze, ManagerOrderSourceApply, SourceCustomerDraft
from services.belzakupki_enrichment_service import (
    BelzakupkiEnrichmentService,
    _amount,
    _customer_unp_from_document,
    _objects_from_text,
    _original_file_type,
    _source_identity,
)
from services.belzakupki_import_service import BelzakupkiImportService


@pytest.fixture(autouse=True)
def mock_registry(monkeypatch):
    monkeypatch.setattr("services.belzakupki_customer_service.fetch_registry_data", AsyncMock(return_value={}))


EXCERPT_455 = (
    "Описание предмета государственной закупки: Техническое обслуживание кондиционеров, "
    "расположенных по адресу: г. Витебск, ул. Суворова, д.42/13 (1-й этаж): "
    "TCL (внутренний блок TAC-12HRIA/VE, наружный блок TACO-12HIA/VE) – 2 шт. "
    "TCL (внутренний блок TAC-24HRIA/E1, наружный блок TACO-24HIA/E1) - 2 шт. "
    "TCL (внутренний блок TAC-18HRIA/E1, наружный блок TACO-18HIA/E1) - 1 шт. "
    "GENERAL CLIMATE (модель: GCEAF09HR/GU-EAF09HRN1) – 1 шт. "
    "Техническое обслуживание кондиционеров, расположенных по адресу: "
    "г.п. Шумилино, ул. Короткина, д.10 (1-й этаж): "
    "Horizont (модель 09H-03) – 1 шт. General (модель ASH12USCCW) – 1 шт. "
    "Итого общее количество кондиционеров подлежащих обслуживанию – 8 шт."
)


def _order() -> Order:
    return Order(
        id=455, tenant_id=1, storefront_id=1, lead_source=LeadSource.BELZAKUPKI,
        technical_meta={"belzakupki": {"source": "goszakupki_by", "external_tender_id": "3707082",
                                      "tender": {"source": "goszakupki_by", "external_id": "3707082"}}},
    )


def _detail(text: str | None = EXCERPT_455):
    return {
        "source": "goszakupki_by", "external_id": "3707082", "title": "Обслуживание кондиционеров",
        "source_url": "https://example.test/455", "estimated_value": "15 000 BYN",
        "customer": {"name": "ОАО Заказчик", "unp": "123456789", "contacts": {
            "phone": "Юрова Екатерина Вячеславовна, +375212210029", "email": "mail@example.test"}},
        "documents": [{"id": 31, "name": "Техническое задание", "source_url": "https://example.test/doc", "extracted_text": text}],
    }


def test_455_document_has_two_objects_and_eight_units():
    assert _source_identity(_order()) == ("goszakupki_by", "3707082")
    objects = _objects_from_text(EXCERPT_455)
    assert [item.address for item in objects] == [
        "г. Витебск, ул. Суворова, д.42/13 (1-й этаж)",
        "г.п. Шумилино, ул. Короткина, д.10 (1-й этаж)",
    ]
    assert [sum(unit.quantity or 0 for unit in obj.equipment) for obj in objects] == [6, 2]
    assert objects[0].equipment[0].model == "TAC-12HRIA/VE"


def test_455_word_table_text_and_malformed_parenthesis_still_yield_eight_units():
    table = (
        "|Описание предмета|Техническое обслуживание|\n"
        "|государственной закупки|кондиционеров, расположенных по|\n"
        "| |адресу: г. Витебск, ул. Суворова, д.42/13|\n"
        "| |(1-й этаж):|\n"
        "| |TCL (внутренний блок TAC-12HRIA/VE,|\n"
        "| |наружный блок TACO-12HIA/VE) – 2 шт.|\n"
        "| |TCL (внутренний блок TAC-24HRIA/E1, наружный блок TACO-24HIA/E1) - 2 шт.|\n"
        "| |TCL (внутренний блок TAC-18HRIA/E1, наружный блок TACO-18HIA/E1 - 1 шт.|\n"
        "| |GENERAL CLIMATE (модель: GCEAF09HR/ |\n"
        "| |GU-EAF09HRN1) – 1 шт.|\n"
        "| |Техническое обслуживание кондиционеров, расположенных по|\n"
        "| |адресу: г.п. Шумилино, ул. Короткина, д.10 (1-й этаж):|\n"
        "| |Horizont (модель 09H-03) – 1 шт.|\n"
        "| |General (модель ASH12USCCW) – 1 шт.|\n"
    )
    objects = _objects_from_text(table)
    assert len(objects) == 2
    assert [sum(unit.quantity or 0 for unit in obj.equipment) for obj in objects] == [6, 2]
    assert objects[0].equipment[3].model == "GCEAF09HR/GU-EAF09HRN1"


def test_import_refresh_preserves_reviewed_enrichment():
    reviewed = {"source": "goszakupki_by", "external_id": "3707082", "work_summary": "Подтверждено"}
    snapshot = {"match_id": 7, "profile": {}, "score": 1, "reason": None, "ai_analysis": None,
                "tender": {"source": "goszakupki_by", "external_id": "3707082"}}
    history = {"prefill-fingerprint": {"product_id": 5, "line_id": 50, "quantity": 9}}
    commands = {"command-1": {"added": [{"product_id": 5}]}}
    updated = BelzakupkiImportService._next_metadata(
        existing={"enrichment": reviewed, "equipment_prefill_history": history, "equipment_prefill_commands": commands}, snapshot=snapshot, snapshot_fingerprint="fingerprint",
    )
    assert updated["enrichment"] == reviewed
    assert updated["equipment_prefill_history"] == history
    assert updated["equipment_prefill_commands"] == commands


def test_source_file_magic_preserves_word_original_type_without_extension():
    ole = bytes.fromhex("d0cf11e0a1b11ae1") + b"original-word-bytes"
    assert _original_file_type(ole, "Техническое задание", "application/octet-stream") == (
        "Техническое задание.doc", "application/msword",
    )
    archive = BytesIO()
    with ZipFile(archive, "w") as zipped:
        zipped.writestr("word/document.xml", "<document/>")
    assert _original_file_type(archive.getvalue(), "spec", "application/octet-stream") == (
        "spec.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def test_source_amount_is_bounded_to_numeric_value():
    assert _amount("15 000 BYN") == 15000.0
    assert _amount("price on request") is None


def test_document_unp_requires_customer_context():
    text = "Поставщик УНП 987654321. Заказчик ОАО Заказчик, УНП 123456789."
    assert _customer_unp_from_document(text, "ОАО Заказчик") == "123456789"
    assert _customer_unp_from_document("Поставщик УНП 987654321", "ОАО Заказчик") is None


@pytest.mark.asyncio
async def test_preview_uses_exact_tenant_unp_and_does_not_write(monkeypatch):
    order = _order()
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_order", AsyncMock(return_value=order))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_detail", AsyncMock(return_value=_detail()))

    class Session:
        get = AsyncMock(return_value=None)
        execute = AsyncMock()
        commit = AsyncMock()

    session = Session()
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = [SimpleNamespace(id=17)]
    preview = await BelzakupkiEnrichmentService.preview(
        session, order_id=455,
        scope=TenantScope(tenant_id=1, storefront_id=1),
    )
    assert preview.existing_customer_id == 17
    assert preview.customer.inn == "123456789"
    assert preview.customer.phone == "+375212210029"
    assert len(preview.objects) == 2
    assert preview.documents[0].download_url.endswith("/source-documents/31")
    assert preview.estimated_value == 15000.0
    session.commit.assert_not_awaited()
    statement = session.execute.await_args.args[0]
    sql = str(statement)
    assert "customer.tenant_id" in sql and "customer.inn" in sql


@pytest.mark.asyncio
async def test_analyze_reads_missing_doc_text_and_returns_ai_draft(monkeypatch):
    order = _order()
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_order", AsyncMock(return_value=order))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_detail", AsyncMock(return_value=_detail(None)))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "document", AsyncMock(return_value=(b"doc", "task.doc", "application/msword")))
    monkeypatch.setattr(
        "services.belzakupki_enrichment_service.extract_missing_document_text",
        AsyncMock(return_value=(EXCERPT_455, None)),
    )
    objects = _objects_from_text(EXCERPT_455)
    ai = AsyncMock(return_value=("Обслуживание восьми кондиционеров", "6 + 2", objects))
    monkeypatch.setattr("services.belzakupki_enrichment_service.analyze_tender_text", ai)

    class Session:
        get = AsyncMock(return_value=None)
        execute = AsyncMock()
        commit = AsyncMock()

    session = Session()
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = []
    preview = await BelzakupkiEnrichmentService.analyze(
        session, order_id=455, scope=TenantScope(tenant_id=1, storefront_id=1),
        payload=ManagerOrderSourceAnalyze(document_ids=["31"]),
    )
    assert preview.analysis_source == "ai"
    assert preview.suggested_scenario.service_type == "maintenance"
    assert preview.analyzed_document_ids == ["31"]
    assert len(preview.objects) == 2
    assert preview.work_summary == "Обслуживание восьми кондиционеров"
    assert preview.field_sources["work_summary"] == "ИИ по выбранным документам"
    assert preview.field_sources["objects.1.address"] == "ИИ по выбранным документам"
    assert preview.field_sources["customer.email"] == "Карточка закупки"
    ai.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_replay_preserves_reviewed_work_and_objects_when_omitted(monkeypatch):
    order = _order()
    order.status = OrderStatus.NEGOTIATION
    reviewed_objects = _objects_from_text(EXCERPT_455)
    order.technical_meta["belzakupki"]["enrichment"] = {
        "source": "goszakupki_by", "external_id": "3707082",
        "work_summary": "Уточнённый менеджером объём работ",
        "equipment_details": "Восемь блоков по двум объектам",
        "objects": [obj.model_dump() for obj in reviewed_objects],
        "customer_branch_ids": [],
    }
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_order", AsyncMock(return_value=order))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_detail", AsyncMock(return_value=_detail()))

    class Session:
        get = AsyncMock(return_value=None)
        execute = AsyncMock()
        commit = AsyncMock()

    session = Session()
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = []
    scope = TenantScope(tenant_id=1, storefront_id=1)
    preview = await BelzakupkiEnrichmentService.preview(session, order_id=455, scope=scope)
    assert preview.analysis_source == "reviewed"
    assert preview.current_scenario.service_type == "turnkey"
    assert preview.suggested_scenario.service_type == "maintenance"
    assert preview.work_summary == "Уточнённый менеджером объём работ"
    assert [sum(unit.quantity or 0 for unit in obj.equipment) for obj in preview.objects] == [6, 2]
    assert preview.field_sources["objects.0.address"] == "Ранее подтверждено менеджером"

    payload = ManagerOrderSourceApply(customer_action="skip", document_ids=[])
    monkeypatch.setattr("services.belzakupki_equipment_prefill.BelzakupkiEquipmentPrefillService.candidates", AsyncMock(return_value=[]))
    for _ in range(2):
        result = await BelzakupkiEnrichmentService.apply(
            session, order_id=455, scope=scope, payload=payload, username="manager",
        )
        assert result.customer_id is None
        assert result.attachment_ids == []
        assert order.technical_meta["belzakupki"]["enrichment"]["work_summary"] == "Уточнённый менеджером объём работ"
        assert len(order.technical_meta["belzakupki"]["enrichment"]["objects"]) == 2
        assert order.status == OrderStatus.NEGOTIATION
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_apply_links_customer_two_branches_and_original_once(monkeypatch):
    order = _order()
    order.status = OrderStatus.NEW_LEAD
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_order", AsyncMock(return_value=order))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_detail", AsyncMock(return_value=_detail()))
    monkeypatch.setattr(
        "services.belzakupki_customer_service.CustomerCreationService._find_duplicate",
        AsyncMock(return_value=None),
    )
    document = AsyncMock(return_value=(b"original-word-bytes", "task.doc", "application/msword"))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "document", document)
    storage = AsyncMock(return_value={"id": 601})
    monkeypatch.setattr(
        "services.belzakupki_enrichment_service.ServiceAttachmentService.create_and_link_order_attachment",
        storage,
    )
    created: list[object] = []

    class Session:
        get = AsyncMock(return_value=None)
        execute = AsyncMock()
        scalar = AsyncMock()
        flush = AsyncMock()
        commit = AsyncMock()

        def add(self, item):
            if isinstance(item, Customer):
                item.id = 501
            elif isinstance(item, CustomerBranch):
                item.id = 700 + len([obj for obj in created if isinstance(obj, CustomerBranch)]) + 1
            created.append(item)

    session = Session()
    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    existing = MagicMock()
    existing.scalars.return_value.all.return_value = [SimpleNamespace(
        id=601, source_meta={"belzakupki_document_id": "31", "external_id": "3707082"},
    )]
    session.execute.side_effect = [MagicMock(), empty, existing]
    session.scalar.side_effect = [None, None, None]
    scope = TenantScope(tenant_id=1, storefront_id=1)
    objects = _objects_from_text(EXCERPT_455)
    first = await BelzakupkiEnrichmentService.apply(
        session, order_id=455, scope=scope,
        payload=ManagerOrderSourceApply(
            customer_action="create",
            customer=SourceCustomerDraft(name="ОАО Заказчик", inn="123456789", type="company"),
            workflow_type="maintenance", service_type="maintenance",
            objects=objects, document_ids=["31"], work_summary="Обслужить 8 блоков",
            analysis_source="ai", analyzed_document_ids=["31"],
        ),
        username="manager",
    )
    assert first.customer_id == 501
    assert first.attachment_ids == [601]
    assert order.status == OrderStatus.NEGOTIATION
    assert order.workflow_type == "maintenance"
    assert order.technical_meta["service_type"] == "maintenance"
    assert "scenario" in first.applied_fields
    branches = [obj for obj in created if isinstance(obj, CustomerBranch)]
    assert len(branches) == 2
    assert branches[0].delivery_address != branches[1].delivery_address
    assert order.customer_branch_id is None
    assert order.technical_meta["belzakupki"]["enrichment"]["analysis_source"] == "ai"
    assert storage.await_args.kwargs["commit"] is False
    assert storage.await_args.kwargs["source_meta"]["belzakupki_document_id"] == "31"

    monkeypatch.setattr(
        "services.belzakupki_enrichment_service.TenantEntityAccessService.get_customer",
        AsyncMock(return_value=next(obj for obj in created if isinstance(obj, Customer))),
    )
    session.scalar.side_effect = branches
    second = await BelzakupkiEnrichmentService.apply(
        session, order_id=455, scope=scope,
        payload=ManagerOrderSourceApply(customer_action="existing", customer_id=501, document_ids=["31"]),
        username="manager",
    )
    assert second.attachment_ids == [601]
    assert len([obj for obj in created if isinstance(obj, CustomerBranch)]) == 2
    assert storage.await_count == 1
    assert document.await_count == 1
    assert order.workflow_type == "maintenance"


@pytest.mark.asyncio
async def test_new_lead_cannot_keep_default_sales_scenario_silently(monkeypatch):
    order = _order()
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_order", AsyncMock(return_value=order))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_detail", AsyncMock(return_value=_detail()))
    session = AsyncMock()
    session.get.return_value = None

    with pytest.raises(ValueError, match="Choose an order scenario"):
        await BelzakupkiEnrichmentService.apply(
            session, order_id=455, scope=TenantScope(tenant_id=1, storefront_id=1),
            payload=ManagerOrderSourceApply(
                customer_action="create",
                customer=SourceCustomerDraft(name="ОАО Заказчик", type="company"),
            ),
            username="manager",
        )
    assert order.workflow_type == "sales_installation"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_rejects_existing_tenant_customer_by_phone_without_unp(monkeypatch):
    order = _order()
    source = _detail()
    source["customer"]["unp"] = None
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_order", AsyncMock(return_value=order))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_detail", AsyncMock(return_value=source))
    duplicate = Customer(id=77, tenant_id=1, name="ОАО Заказчик", phone="+375212210029")
    checker = AsyncMock(return_value=(duplicate, ("phone",)))
    monkeypatch.setattr(
        "services.belzakupki_customer_service.CustomerCreationService._find_duplicate",
        checker,
    )

    class Session:
        get = AsyncMock(return_value=None)
        execute = AsyncMock()
        commit = AsyncMock()

    session = Session()
    with pytest.raises(ValueError, match="уже существует"):
        await BelzakupkiEnrichmentService.apply(
            session, order_id=455, scope=TenantScope(tenant_id=1, storefront_id=1),
            payload=ManagerOrderSourceApply(
                customer_action="create",
                workflow_type="maintenance", service_type="maintenance",
                customer=SourceCustomerDraft(name="ОАО Заказчик", phone="+375212210029", type="company"),
            ),
            username="manager",
        )
    assert checker.await_args.kwargs["tenant_scope"].tenant_id == 1
    session.commit.assert_not_awaited()
