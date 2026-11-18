from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from core.command_actor import CommandActor
from models import LeadSource, Order
from models.tenancy import TenantScope
from schemas_belzakupki_enrichment import ManagerOrderSourceCard, SourceOriginalFile
from schemas_tender_document_reader import TenderDocumentReadResult, TenderDocumentFragment
from schemas_connector_tender_review import TenderSourcePreviewInput
from services import connector_tender_analysis as analysis, connector_tender_preview as preview
from services.belzakupki_import_service import BelzakupkiImportService
from services.connector_mcp_tools import TOOLS, execute_tool
from services.tender_source_reference import resolve_source_reference


ACTOR = CommandActor(2, "owner", TenantScope(1, 1, is_system=True), "chatgpt")
DIGEST = "c" * 64


def setup_source(monkeypatch):
    tender = {"source": "goszakupki_by", "external_id": "3837466", "title": "Модернизация здания",
              "url": "https://goszakupki.by/single-source/view/3837466", "deadline_kind": "submission"}
    order = Order(id=657, title=tender["title"], lead_source=LeadSource.BELZAKUPKI,
                  technical_meta={"belzakupki": {"tender": tender}})
    card = ManagerOrderSourceCard(order_id=657, source=tender["source"], external_id=tender["external_id"])
    data = {"source": tender["source"], "external_id": tender["external_id"],
            "deadline_at": "2026-11-18T20:59:00Z", "estimated_value": "2 065,96 BYN",
            "objects": [{"number": "1", "name": "Обслуживание"}, {"number": "2", "name": "Монтаж"}],
            "documents": [{"id": "a", "name": "ТЗ.pdf", "extracted_text": "Обслуживание", "extracted_text_truncated": True,
                           "source_url": "https://private.test/download?token=topsecret"},
                          {"id": "b", "name": "Скан.pdf", "extracted_text": None}]}
    monkeypatch.setattr(preview.BelzakupkiEnrichmentService, "_order", AsyncMock(return_value=order))
    monkeypatch.setattr(preview.BelzakupkiSourceEquipmentService, "card", AsyncMock(return_value=card))
    monkeypatch.setattr(preview.BelzakupkiEnrichmentService, "_detail", AsyncMock(return_value=data))
    return order, card, data


@pytest.mark.asyncio
async def test_tender_preview_pages_lots_originals_and_source_dates(monkeypatch):
    setup_source(monkeypatch)
    args = {"order_id": 657, "limit": 1}
    first = await execute_tool(None, ACTOR, TOOLS["get_tender_source_preview"], args)
    second = await execute_tool(None, ACTOR, TOOLS["get_tender_source_preview"], {**args, "page": 2})
    assert first["procedure_type"] == "single-source"
    assert first["deadline_at"].endswith("Z") and first["deadline_kind"] == "submission"
    assert [first["lots"][0]["number"], second["lots"][0]["number"]] == ["1", "2"]
    assert first["documents"][0]["source_text_truncated"] and not second["documents"][0]["has_source_text"]
    assert first["next_page"] == 2 and second["next_page"] is None
    assert "private.test" not in str(first) and "topsecret" not in str(first)


@pytest.mark.asyncio
async def test_missing_remote_inventory_returns_only_saved_originals_with_warning(monkeypatch):
    _, card, _ = setup_source(monkeypatch)
    card.originals.append(SourceOriginalFile(attachment_id=42, document_id="saved", name="ТЗ.doc", mime_type="application/msword"))
    monkeypatch.setattr(preview.BelzakupkiEnrichmentService, "_detail", AsyncMock(side_effect=httpx.ConnectError("private URL")))
    result = await preview.get_tender_source_preview(None, ACTOR, TenderSourcePreviewInput(order_id=657))
    assert not result.inventory_complete and result.documents[0].saved_original and result.warnings
    assert "private URL" not in str(result)


@pytest.mark.asyncio
async def test_analyze_selected_documents_via_catalog_grounds_partial_result(monkeypatch):
    setup_source(monkeypatch)
    monkeypatch.setattr(analysis, "require_analysis_access", AsyncMock())
    sentence = "Техническое обслуживание кондиционеров."
    files = [TenderDocumentReadResult(order_id=657, document_id="a", filename="ТЗ.pdf", sha256=DIGEST,
                                      status="complete", total_chars=len(sentence), origin="source",
                                      fragments=[TenderDocumentFragment(page=2, fragment=1, offset=0, text=sentence, method="embedded")]),
             TenderDocumentReadResult(order_id=657, document_id="b", status="unavailable", diagnostics=["Нет оригинала."])]
    monkeypatch.setattr(analysis, "load_tender_document", AsyncMock(side_effect=files))
    provider_call = AsyncMock(return_value=('{"facts":[]}', 'gpt-5.4-mini'))
    monkeypatch.setattr("services.tender_qualification.request_openai_tender_completion", provider_call)
    result = await execute_tool(None, ACTOR, TOOLS["analyze_tender_documents"], {
        "order_id": 657, "document_ids": ["a", "b"], "profile_name": "mvn_vitebsk"})
    report = result["qualification"]
    assert report["provider"] == "openai" and report["extraction_status"] == "completed"
    assert report["decision"] == "review" and not report["complete"]
    assert result["documents"][1]["status"] == "unavailable" and result["unselected_count"] == 0
    work = next(f for f in report["facts"] if f["kind"] == "work_scope")
    assert work["evidence"]["document_sha256"] == DIGEST and work["evidence"]["location"] == "стр. 2, фрагмент 1"
    assert any(f["kind"] == "estimated_budget" and f["source"] == "procedure_metadata" for f in report["facts"])
    assert result["external_id"] == "3837466" and report["model"] == "gpt-5.4-mini"
    provider_call.assert_awaited_once()


def test_native_selector_only_accepts_verified_refs_of_this_order(monkeypatch):
    order, _, _ = setup_source(monkeypatch)
    key = BelzakupkiImportService._order_fingerprint(source="gias", external_id="uuid-1")
    with pytest.raises(LookupError):
        resolve_source_reference(order, key)
    alternate = {"source": "gias", "external_id": "uuid-1"}
    order.technical_meta["belzakupki"]["source_references"] = {key: alternate}
    assert resolve_source_reference(order, key) == ("gias", "uuid-1")
    alternate["claimed_canonical_url"] = "https://goszakupki.by/marketing/view/123"
    with pytest.raises(LookupError):
        resolve_source_reference(order, key)


@pytest.mark.asyncio
async def test_unbound_staff_in_system_tenant_cannot_trigger_analysis(monkeypatch):
    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id=2)))
    monkeypatch.setattr(analysis.LegacyOwnerAuthGuard, "state", AsyncMock(return_value=object()))
    monkeypatch.setattr(analysis.LegacyOwnerManagedIdentityService, "exact_bound_staff_identity_allowed", AsyncMock(return_value=False))
    with pytest.raises(PermissionError):
        await analysis.require_analysis_access(session, ACTOR)
