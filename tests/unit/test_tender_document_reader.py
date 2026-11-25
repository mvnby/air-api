import hashlib
import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from zipfile import ZipFile

import httpx
import pytest
from docx import Document
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy.dialects import postgresql

from models import LeadSource, Order, ServiceAttachment
from models.tenancy import TenantScope
from schemas_tender_document_reader import TenderDocumentReadInput
from services import tender_document_reader as reader
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService, SourceDocumentNotFound, SourceDocumentTooLarge
from services.belzakupki_import_service import BelzakupkiImportService
from services.private_attachment_storage_service import (
    LocalPrivateAttachmentStorage, PrivateAttachmentTooLarge, S3PrivateAttachmentStorage,
)


SCOPE = TenantScope(tenant_id=3, storefront_id=4)


def _docx() -> bytes:
    document = Document()
    document.add_paragraph("До таблицы")
    cells = document.add_table(rows=1, cols=2).rows[0].cells
    cells[0].text = "Кондиционер TAC-12"
    cells[1].text = "8 шт."
    document.add_paragraph("После таблицы")
    document.sections[0].footer.paragraphs[0].text = "Условия оплаты"
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _pdf(*, raster: bool) -> bytes:
    output = BytesIO()
    pdf = Canvas(output)
    pdf.drawString(50, 720, "Page one: embedded tender evidence")
    pdf.showPage()
    if raster:
        scan = Image.new("RGB", (1000, 350), "white")
        ImageDraw.Draw(scan).text((40, 90), "SCAN: QUANTITY 8", fill="black", font=ImageFont.load_default(size=70))
        pdf.drawImage(ImageReader(scan), 50, 470, width=500, height=175)
    pdf.drawString(50, 56, "Page two: embedded footer")
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def _xlsx(*, with_formula: bool = False) -> bytes:
    book = Workbook()
    book.active.title = "Смета"
    book.active["B3"] = "Монтаж сплит-системы"
    book.active["C3"] = 2
    if with_formula:
        book.active["D3"] = "=C3*100"
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def test_archive_keeps_sheet_rows_word_sections_and_unreadable_members(tmp_path):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("Документы/ТЗ.docx", _docx())
        archive.writestr("Смета.xlsx", _xlsx(with_formula=True))
        archive.writestr("Чертёж.dwg", b"unsupported")
    result = reader._extract_original(output.getvalue(), "zip", tmp_path)
    assert result["status"] == "partial"
    assert any("Чертёж.dwg" in line for line in result["diagnostics"])
    assert any("значения формул" in line for line in result["diagnostics"])
    parts = result["fragments"]
    assert parts[0]["section"] == "Документы/ТЗ.docx · word/document.xml"
    assert parts[-1]["section"] == "Смета.xlsx · Лист «Смета», строка 3"
    assert parts[-1]["text"].strip() == "Монтаж сплит-системы | 2"
    assert parts[-1]["offset"] == sum(len(part["text"]) for part in parts[:-1])


def test_xlsx_sheet_limit_does_not_claim_full_coverage(monkeypatch, tmp_path):
    normal = reader._extract_original(_xlsx(), "xlsx", tmp_path)
    assert normal["status"] == "complete"
    monkeypatch.setattr(reader, "MAX_WORKBOOK_ROWS", 3)
    book = Workbook()
    book.active["B3"] = "Монтаж"
    book.active["B4"] = "Демонтаж"
    output = BytesIO()
    book.save(output)
    book.close()
    limited = reader._extract_original(output.getvalue(), "xlsx", tmp_path)
    assert limited["status"] == "partial"
    assert [fragment["text"] for fragment in limited["fragments"]] == ["Монтаж"]
    assert "до 3 строк" in limited["diagnostics"][0]


def test_long_archive_member_leaves_budget_for_spreadsheet(monkeypatch, tmp_path):
    source = Document()
    source.add_paragraph("Длинная спецификация " * 50)
    output = BytesIO()
    source.save(output)
    archive_bytes = BytesIO()
    with ZipFile(archive_bytes, "w") as archive:
        archive.writestr("Проект.docx", output.getvalue())
        archive.writestr("Смета.xlsx", _xlsx())
    monkeypatch.setattr(reader, "MAX_TEXT_CHARS", 100)
    result = reader._extract_original(archive_bytes.getvalue(), "zip", tmp_path)
    assert result["status"] == "partial"
    assert result["total_chars"] <= reader.MAX_TEXT_CHARS
    assert result["fragments"][-1]["section"] == "Смета.xlsx · Лист «Смета», строка 3"


@pytest.mark.asyncio
async def test_reads_original_docx_in_order_and_reassembles_pages(monkeypatch):
    original = _docx()
    fetch = AsyncMock(return_value=(original, "Техническое задание.docx", reader.WORD_MIME))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "document", fetch)
    session = MagicMock()
    inputs = TenderDocumentReadInput(order_id=455, document_id="31", limit=15)
    first = await reader.read_tender_document(session, SCOPE, inputs)
    assert first.status == "complete" and first.origin == "source"
    assert first.sha256 == hashlib.sha256(original).hexdigest()
    assert first.next_offset == 15
    assert fetch.await_args.args == (session,)
    assert fetch.await_args.kwargs == {
        "order_id": 455, "document_id": "31", "scope": SCOPE, "max_bytes": reader.MAX_ORIGINAL_BYTES,
    }

    rest = await reader.read_tender_document(
        session, SCOPE, TenderDocumentReadInput(order_id=455, document_id="31", offset=15, sha256=first.sha256),
    )
    assert rest.next_offset is None
    assert [(item.fragment, item.section) for item in rest.fragments] == [
        (2, "word/document.xml"), (3, "word/document.xml"), (4, "word/footer1.xml"),
    ]
    assert rest.fragments[0].offset == 15
    assert "".join(item.text for item in first.fragments + rest.fragments) == (
        "До таблицы\n\nКондиционер TAC-12 | 8 шт.\n\nПосле таблицы\n\nУсловия оплаты"
    )

    fetch.return_value = (b"changed", "Техническое задание.docx", reader.WORD_MIME)
    with pytest.raises(ValueError, match="Оригинал изменился"):
        await reader.read_tender_document(
            session, SCOPE, TenderDocumentReadInput(order_id=455, document_id="31", offset=15, sha256=first.sha256),
        )


def test_continuation_requires_original_hash_and_forbids_urls():
    with pytest.raises(ValidationError):
        TenderDocumentReadInput(order_id=455, document_id="31", offset=1)
    with pytest.raises(ValidationError):
        TenderDocumentReadInput.model_validate({"order_id": 455, "document_id": "31", "url": "https://private.test/a"})


def test_pdf_preserves_real_page_numbers(tmp_path):
    result = reader._extract_original(_pdf(raster=False), "pdf", tmp_path)
    assert result["status"] == "complete"
    assert [(part["page"], part["method"]) for part in result["fragments"]] == [(1, "embedded"), (2, "embedded")]
    assert "embedded footer" in result["fragments"][1]["text"]


def test_mixed_pdf_ocr_is_page_specific_and_failure_is_visible(monkeypatch, tmp_path):
    def recognize(source, page):
        assert source.read_bytes().startswith(b"%PDF-")
        assert page == 2
        return "SCAN: QUANTITY 8\nPage two:  embedded footer", True

    monkeypatch.setattr(reader, "_recognize_pdf_page", recognize)
    pdf = _pdf(raster=True)
    result = reader._extract_original(pdf, "pdf", tmp_path)
    assert result["status"] == "complete"
    assert [(part["page"], part["method"]) for part in result["fragments"]] == [(1, "embedded"), (2, "embedded"), (2, "ocr")]
    text = "".join(part["text"] for part in result["fragments"])
    assert text.count("embedded footer") == 1
    assert "SCAN: QUANTITY 8" in text
    assert result["fragments"][2]["offset"] == len(result["fragments"][0]["text"] + result["fragments"][1]["text"])
    assert result["total_chars"] == len(text)

    # OCR returned a different clause and no overlapping embedded text.
    monkeypatch.setattr(reader, "_recognize_pdf_page", lambda _source, _page: ("SCAN: QUANTITY 8", False))
    weak = reader._extract_original(pdf, "pdf", tmp_path)
    assert weak["status"] == "partial"
    assert "низкая уверенность OCR" in weak["diagnostics"][0]
    assert "embedded footer" in weak["fragments"][1]["text"]
    assert "SCAN: QUANTITY 8" in weak["fragments"][2]["text"]

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("tesseract", 4)

    monkeypatch.setattr(reader, "_recognize_pdf_page", timeout)
    result = reader._extract_original(pdf, "pdf", tmp_path)
    assert result["status"] == "partial"
    assert "Страница 2" in result["diagnostics"][0]
    assert result["fragments"][1]["method"] == "embedded"


def test_ocr_quality_requires_parseable_word_confidence(tmp_path):
    report = tmp_path / "page.tsv"
    report.write_text("level\tconf\ttext\n1\t-1\t\n5\t91.5\tQUANTITY\n5\t89.0\t8\n", encoding="utf-8")
    assert reader._reliable_ocr_words(report)
    report.write_text("level\tconf\ttext\n5\t91.5\tQUANTITY\n5\t20.0\t8\n", encoding="utf-8")
    assert not reader._reliable_ocr_words(report)


@pytest.mark.skipif(not shutil.which("pdftoppm") or not shutil.which("tesseract"), reason="PDF OCR runtime is unavailable")
@pytest.mark.asyncio
async def test_real_pdf_ocr_worker_reads_a_scan_alongside_embedded_text():
    result = await reader._extract_in_worker(_pdf(raster=True), "pdf")
    assert result["status"] in {"complete", "partial"}
    assert result["fragments"][1]["method"] == "embedded"
    assert result["fragments"][2]["method"] == "ocr"
    assert "QUANTITY 8" in result["fragments"][2]["text"]


def test_doc_uses_antiword_utf8_and_preserves_table_output(monkeypatch, tmp_path):
    legacy_doc = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

    def antiword(command, *, stdout, timeout, **kwargs):
        assert command[:5] == ["antiword", "-m", "UTF-8.txt", "-w", "0"]
        assert Path(command[5]).read_bytes() == legacy_doc
        assert timeout == 8
        stdout.write("Адрес\n| TAC-12 | 8 шт. |\nИтого".encode())

    monkeypatch.setattr(reader.subprocess, "run", antiword)
    result = reader._extract_original(legacy_doc, "doc", tmp_path)
    assert result["status"] == "complete"
    assert result["fragments"][0]["method"] == "doc"
    assert result["fragments"][0]["text"].splitlines() == ["Адрес", "| TAC-12 | 8 шт. |", "Итого"]


def test_docx_expansion_and_text_cutoffs_are_explicit(monkeypatch, tmp_path):
    docx = _docx()
    monkeypatch.setattr(reader, "MAX_TEXT_CHARS", 17)
    result = reader._extract_original(docx, "docx", tmp_path)
    assert result["status"] == "partial"
    assert result["total_chars"] == 17
    assert "лимит текста" in result["diagnostics"][0]
    monkeypatch.setattr(reader, "MAX_WORD_EXPANDED_BYTES", 100)
    assert reader._extract_original(docx, "docx", tmp_path)["status"] == "oversized"


def test_parser_rejects_invalid_or_entity_bearing_documents(tmp_path):
    assert reader._extract_original(b"broken PDF", "pdf", tmp_path)["status"] == "unreadable"
    archive = BytesIO()
    with ZipFile(archive, "w") as docx:
        docx.writestr("word/document.xml", '<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>')
    result = reader._extract_original(archive.getvalue(), "docx", tmp_path)
    assert result["status"] == "unreadable"
    assert result["fragments"] == []


@pytest.mark.asyncio
async def test_saved_original_requires_scope_and_matching_digest(monkeypatch, tmp_path):
    content = _docx()
    hash_value = hashlib.sha256(content).hexdigest()
    backend = LocalPrivateAttachmentStorage(tmp_path)
    stored = await backend.save(content=content, content_hash=hash_value, extension="docx", content_type=reader.WORD_MIME, variant="original")
    attachment = ServiceAttachment(
        id=7, original_filename="saved.docx", size_bytes=len(content), content_hash=hash_value, storage_key=stored.storage_key,
        mime_type=reader.WORD_MIME,
    )
    scoped_order = AsyncMock(return_value=Order(
        id=455, lead_source=LeadSource.BELZAKUPKI,
        technical_meta={"belzakupki": {"source": "goszakupki_by", "external_tender_id": "3707082"}},
    ))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_order", scoped_order)
    monkeypatch.setattr(BelzakupkiEnrichmentService, "document", AsyncMock(side_effect=httpx.ConnectError("source unavailable")))
    monkeypatch.setattr("services.private_attachment_storage_service.get_private_attachment_storage", lambda _provider: backend)
    session = MagicMock(scalar=AsyncMock(return_value=attachment))

    result = await reader.load_tender_document(session, SCOPE, order_id=455, document_id="31")
    scoped_order.assert_awaited_once_with(session, 455, SCOPE)
    query = session.scalar.await_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    assert "order_attachment_link.order_id = 455" in str(query)
    assert "order_attachment_link.archived_at IS NULL" in str(query)
    assert "service_attachment.archived_at IS NULL" in str(query)
    assert all(value in str(query) for value in ["'goszakupki_by'", "'3707082'", "'belzakupki_document_id'", "'31'", "'tender_original'"])
    assert result.origin == "saved_original" and result.attachment_id == 7
    assert result.sha256 == hash_value and result.status == "complete"
    assert stored.storage_key not in result.model_dump_json()

    BelzakupkiEnrichmentService.document.side_effect = SourceDocumentNotFound("Original disappeared from source")
    result = await reader.load_tender_document(session, SCOPE, order_id=455, document_id="31")
    assert result.origin == "saved_original" and result.status == "complete"

    attachment.content_hash = "0" * 64
    unavailable = await reader.load_tender_document(session, SCOPE, order_id=455, document_id="31")
    assert unavailable.status == "unavailable" and unavailable.fragments == []

    session.scalar.reset_mock()
    scoped_order.side_effect = LookupError("Order not found")
    with pytest.raises(LookupError, match="Order not found"):
        await reader.load_tender_document(session, SCOPE, order_id=455, document_id="31")
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_oversized_inventory_uses_saved_original_but_oversized_file_stops(monkeypatch):
    order = Order(id=455, lead_source=LeadSource.BELZAKUPKI, technical_meta={"belzakupki": {
        "source": "goszakupki_by", "external_tender_id": "3707082",
    }})
    detail = AsyncMock(side_effect=SourceDocumentTooLarge("Inventory exceeded the limit"))
    fetch = AsyncMock(side_effect=SourceDocumentTooLarge("Original exceeded the limit"))
    read_saved = AsyncMock(return_value=(_docx(), "saved.docx", reader.WORD_MIME, 7))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_order", AsyncMock(return_value=order))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_detail", detail)
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_fetch", fetch)
    monkeypatch.setattr(reader, "_read_saved_original", read_saved)
    session = MagicMock()

    result = await reader.load_tender_document(session, SCOPE, order_id=455, document_id="31")
    assert result.status == "complete" and result.origin == "saved_original"
    read_saved.assert_awaited_once_with(session, SCOPE, order_id=455, document_id="31", source_reference=None)
    fetch.assert_not_awaited()

    detail.side_effect = None
    detail.return_value = {"documents": [{"id": "31", "name": "ТЗ"}]}
    read_saved.reset_mock()
    result = await reader.load_tender_document(session, SCOPE, order_id=455, document_id="31")
    assert result.status == "oversized" and not result.fragments
    fetch.assert_awaited_once()
    read_saved.assert_not_awaited()


@pytest.mark.asyncio
async def test_reader_verifies_attachment_membership_under_exact_source_reference(monkeypatch):
    alternate = {"source": "goszakupki_by", "external_id": "alternate"}
    reference = BelzakupkiImportService._order_fingerprint(**alternate)
    order = Order(id=455, lead_source=LeadSource.BELZAKUPKI, technical_meta={"belzakupki": {
        "source": "goszakupki_by", "external_tender_id": "primary", "source_references": {reference: alternate},
    }})
    scoped_order = AsyncMock(return_value=order)
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_order", scoped_order)
    fetch = AsyncMock(side_effect=[
        httpx.Response(200, json={**alternate, "documents": [{"id": "31", "name": "ТЗ"}]}),
        httpx.Response(200, headers={"content-type": "application/pdf"}, content=_pdf(raster=False)),
    ])
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_fetch", fetch)
    session = MagicMock()

    with pytest.raises(LookupError, match="Source reference not found"):
        await reader.load_tender_document(session, SCOPE, order_id=455, document_id="31", source_reference="0" * 64)
    fetch.assert_not_awaited()
    result = await reader.load_tender_document(session, SCOPE, order_id=455, document_id="31", source_reference=reference)
    assert result.status == "complete" and result.source_reference == reference
    assert [call.args for call in fetch.await_args_list] == [
        ("goszakupki_by", "alternate"), ("goszakupki_by", "alternate", "31"),
    ]


@pytest.mark.asyncio
async def test_private_local_read_is_bounded(tmp_path):
    backend = LocalPrivateAttachmentStorage(tmp_path)
    content = b"a" * 100
    original = await backend.save(
        content=content, content_hash=hashlib.sha256(content).hexdigest(), extension="pdf", content_type="application/pdf",
        variant="original",
    )
    assert await backend.read_bounded(original.storage_key, 100) == content
    with pytest.raises(PrivateAttachmentTooLarge):
        await backend.read_bounded(original.storage_key, 99)


@pytest.mark.asyncio
async def test_private_s3_read_caps_range_and_closes_the_body():
    body = BytesIO(b"next")
    client = MagicMock()
    client.get_object.return_value = {"Body": body}
    backend = S3PrivateAttachmentStorage(
        bucket="private", endpoint_url="https://s3.example.test", access_key_id="test-key", secret_access_key="test-secret",
        region="auto", key_prefix="", client=client,
    )
    with pytest.raises(PrivateAttachmentTooLarge):
        await backend.read_bounded("original", 3)
    client.get_object.assert_called_once_with(Bucket="private", Key="original", Range="bytes=0-3")
    assert body.closed


@pytest.mark.asyncio
async def test_source_transport_caps_unknown_length_stream(monkeypatch):
    import services.belzakupki_enrichment_service as enrichment

    read_sizes = []

    class DocumentStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for value in range(3):
                read_sizes.append(value)
                yield b"x" * 65536

    async def upstream(request):
        assert request.url.path == "/api/v1/tenders/source/external/documents/31"
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, stream=DocumentStream())

    async_client = httpx.AsyncClient
    monkeypatch.setattr(enrichment.settings, "BELZAKUPKI_API_BASE_URL", "https://source.test")
    monkeypatch.setattr(enrichment.settings, "BELZAKUPKI_INTEGRATION_KEY", "test")
    monkeypatch.setattr(enrichment.httpx, "AsyncClient", lambda **kwargs: async_client(transport=httpx.MockTransport(upstream), **kwargs))
    with pytest.raises(SourceDocumentTooLarge):
        await BelzakupkiEnrichmentService._fetch("source", "external", "31", max_bytes=65536)
    assert read_sizes == [0, 1]
