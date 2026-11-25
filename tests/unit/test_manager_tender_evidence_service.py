from collections import OrderedDict
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from models import LeadSource, Order
from models.tenancy import TenantScope
from services import manager_tender_evidence_service as jobs
from services import tender_document_reader as reader
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService
from services.belzakupki_import_service import BelzakupkiImportService
from services.deepseek_provider_service import DefectActAIProviderError
from schemas_tender_qualification import TenderDocumentFragment
from services.manager_tender_evidence_service import ManagerTenderEvidenceService as Evidence
from services.tender_qualification import qualify_tender_documents

SCOPE = TenantScope(tenant_id=3, storefront_id=4, is_system=True)
MIRROR = ("goszakupki_by", "3876716")
URL = "https://goszakupki.by/single-source/view/3876716"
WORK = "Демонтаж и установка существующей сплит-системы."


@pytest.fixture
def tender(monkeypatch):
    reference = BelzakupkiImportService._order_fingerprint(source=MIRROR[0], external_id=MIRROR[1])
    order = Order(id=699, lead_source=LeadSource.BELZAKUPKI, technical_meta={"belzakupki": {
        "source": "gias_by", "external_tender_id": "GIAS-699", "canonical_url": URL,
        "source_references": {reference: {"source": MIRROR[0], "external_id": MIRROR[1], "url": URL}},
    }})
    inventory = [{"id": "a", "name": "Задание.pdf"}, {"id": "b", "name": "Условия.pdf"}]
    versions = {"a": b"work-v1", "b": b"terms"}

    @asynccontextmanager
    async def session_factory():
        yield MagicMock(scalar=AsyncMock(return_value=None))

    async def fetch(source, external_id, document_id=None, *, max_bytes=None):
        assert (source, external_id) == MIRROR
        if document_id is None:
            return httpx.Response(200, json={
                "source": source, "external_id": external_id, "source_url": URL, "documents": inventory,
            })
        assert max_bytes == reader.MAX_ORIGINAL_BYTES
        return httpx.Response(200, content=b"%PDF-" + versions[document_id])

    async def parse(content, kind):
        assert kind == "pdf"
        text = WORK if b"work" in content else "Предложение направить на электронную почту."
        return {"status": "complete", "total_chars": len(text), "fragments": [
            {"method": "embedded", "page": 2, "fragment": 1, "offset": 0, "text": text},
        ]}

    fake_fetch = AsyncMock(side_effect=fetch)
    fake_parse = AsyncMock(side_effect=parse)
    provider = AsyncMock(return_value=([
        {"kind": "work_scope", "fragment": 0, "quote": WORK},
        {"kind": "equipment_count", "fragment": 0, "quote": "40 сплит-систем"},
    ], "fixture"))
    monkeypatch.setattr(Evidence, "_jobs", {})
    monkeypatch.setattr(Evidence, "_analyses", OrderedDict())
    monkeypatch.setattr(reader, "_extraction_cache", OrderedDict())
    monkeypatch.setattr(jobs, "async_session_maker", session_factory)
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_order", AsyncMock(return_value=order))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_detail", AsyncMock(return_value={"documents": []}))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_fetch", fake_fetch)
    monkeypatch.setattr(reader, "_extract_in_worker", fake_parse)
    monkeypatch.setattr("services.tender_qualification._request_candidates", provider)
    return fake_fetch, fake_parse, provider, inventory, versions


async def _finish(job):
    await Evidence._jobs[job.job_id].task
    return Evidence.get(order_id=699, scope=SCOPE, job_id=job.job_id)


@pytest.mark.asyncio
async def test_verified_mirror_uses_original_hash_and_coalesces_same_selection(tender):
    fetch, parse, provider, _, versions = tender
    first = Evidence.start(order_id=699, scope=SCOPE, document_ids=["b", "a"])
    duplicate = Evidence.start(order_id=699, scope=SCOPE, document_ids=["a", "b", "a"])
    assert duplicate.job_id == first.job_id and first.status == "reading"
    assert Evidence.get(order_id=699, scope=TenantScope(tenant_id=17, storefront_id=4), job_id=first.job_id) is None
    assert Evidence.get(order_id=699, scope=TenantScope(tenant_id=3, storefront_id=5), job_id=first.job_id) is None
    assert Evidence.get(order_id=661, scope=SCOPE, job_id=first.job_id) is None
    done = await _finish(first)
    assert done.status == "completed" and done.processed == done.total == 2
    assert done.report.document_coverage_complete
    assert done.report.unselected_count == 0
    assert [file.document_id for file in done.report.documents] == ["a", "b"]
    assert any(fact.evidence.quote == WORK and fact.evidence.location == "стр. 2, фрагмент 1"
               for fact in done.report.findings)
    assert all("40" not in fact.evidence.quote for fact in done.report.findings)
    assert [call.args for call in fetch.await_args_list] == [MIRROR, (*MIRROR, "a"), (*MIRROR, "b")]

    reopened = await _finish(Evidence.start(order_id=699, scope=SCOPE, document_ids=["a", "b"]))
    assert reopened.report == done.report
    assert parse.await_count == 2
    assert provider.await_count == 1

    versions["a"] = b"work-v2"
    updated = await _finish(Evidence.start(order_id=699, scope=SCOPE, document_ids=["a", "b"]))
    assert updated.report.documents[0].sha256 != reopened.report.documents[0].sha256
    assert parse.await_count == 3
    assert provider.await_count == 2


@pytest.mark.asyncio
async def test_provider_failure_has_evidence_and_can_retry_without_rereading_unchanged_bytes(tender):
    _, parse, provider, _, _ = tender
    provider.side_effect = [
        DefectActAIProviderError("Unavailable", status=503, retryable=True, code="provider_unavailable"), ([], "fixture"),
    ]
    failed = await _finish(Evidence.start(order_id=699, scope=SCOPE, document_ids=["a"]))
    assert failed.status == "completed" and failed.report.analysis_status == "local_evidence_only"
    assert failed.report.unselected_count == 1 and not failed.report.document_coverage_complete
    assert any(fact.evidence.quote == WORK for fact in failed.report.findings)
    recovered = await _finish(Evidence.start(order_id=699, scope=SCOPE, document_ids=["a"]))
    assert recovered.report.analysis_status == "completed"
    assert parse.await_count == 1 and provider.await_count == 2


@pytest.mark.asyncio
async def test_missing_original_and_changed_inventory_do_not_hide_other_results(tender):
    _, _, provider, inventory, versions = tender
    del versions["b"]
    fetch = BelzakupkiEnrichmentService._fetch
    original = fetch.side_effect

    async def during_outage(*args, **kwargs):
        if len(args) == 3 and args[2] == "b":
            raise httpx.ConnectError("Unavailable original")
        return await original(*args, **kwargs)

    fetch.side_effect = during_outage
    done = await _finish(Evidence.start(order_id=699, scope=SCOPE, document_ids=["a", "b"]))
    assert done.report.documents[1].status == "unavailable"
    assert not done.report.document_coverage_complete
    assert any(fact.evidence.quote == WORK for fact in done.report.findings)
    inventory.pop()
    stale = await _finish(Evidence.start(order_id=699, scope=SCOPE, document_ids=["a", "b"]))
    assert stale.status == "failed" and stale.report is None and "изменился" in stale.error
    assert provider.await_count == 1


@pytest.mark.asyncio
async def test_relocation_and_source_table_addresses_are_found_without_ai():
    fragments = [
        "Место нахождения (для юридического лица) | Витебская область, г. Лепель, пл. Свободы, 11/2",
        "Наименование товаров (работ, услуг) | Текущий ремонт помещений (перенос кондиционера)",
        "Место поставки товаров (выполнения работ, оказания услуг) | Витебская область, г. Лепель, пл. Свободы, 1",
    ]
    result = await qualify_tender_documents(
        [TenderDocumentFragment(document_id="699", filename="Запрос.docx", text=text) for text in fragments],
        provider_timeout_seconds=0,
    )
    assert [(fact.work_type, fact.evidence.quote) for fact in result.facts if fact.kind == "work_scope"] == [
        ("installation", fragments[1]),
    ]
    assert [fact.evidence.quote for fact in result.facts if fact.kind == "execution_address"] == [fragments[2]]


@pytest.mark.asyncio
async def test_wrapped_pdf_preserves_remount_clause_and_maintenance_subject():
    remount = (
        "Необходимо демонтировать исправную сплит-систему из ранее занимаемого здания по\n"
        "адресу: г. Лепель, пл. Свободы 11-2 и монтаж указанного оборудования на существующее штатное место."
    )
    maintenance = "Наименование предмета: Техническое обслуживание систем\nкондиционирования."
    portable = "Поставка переносного кондиционера в количестве 2 шт."
    result = await qualify_tender_documents(
        [TenderDocumentFragment(document_id="1", filename="Документы.pdf", text=text)
         for text in (remount, maintenance, portable)],
        provider_timeout_seconds=0,
    )
    assert {(fact.work_type, fact.evidence.quote) for fact in result.facts if fact.kind == "work_scope"} == {
        ("installation", remount), ("maintenance", maintenance),
    }
