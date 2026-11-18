"""Bounded extraction of original Belzakupki evidence without updating CRM."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import BadZipFile, ZipFile

import httpx

from schemas_tender_document_reader import TenderDocumentFragment, TenderDocumentReadInput, TenderDocumentReadResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.tenancy import TenantScope

MAX_ORIGINAL_BYTES = 12 * 1024 * 1024
MAX_TEXT_CHARS = 180000
MAX_FRAGMENTS = 2000
MAX_WINDOW_FRAGMENTS = 100
MAX_PDF_PAGES = 40
MAX_OCR_PAGES = 6
MIN_OCR_WORD_CONFIDENCE = 55
MAX_WORD_ENTRIES = 500
MAX_WORD_EXPANDED_BYTES = 48 * 1024 * 1024
MAX_PARSER_SECONDS = 45
_parser_slots = asyncio.Semaphore(2)

WORD_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DRAWING_EXTENT = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"
DRAWING_IMAGE = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
WORD_SUPPLEMENTS = re.compile(r"word/(?:header\d+|footer\d+|footnotes|endnotes)\.xml")
WORD_WRAPPERS = {WORD_NS + tag for tag in ("sdt", "sdtContent", "customXml", "ins")}
WORD_BLOCK_WRAPPERS = WORD_WRAPPERS | {WORD_NS + tag for tag in ("body", "footnote", "endnote")}


class _Extraction:
    def __init__(self) -> None:
        self.fragments: list[TenderDocumentFragment] = []
        self.diagnostics: list[str] = []
        self.total_chars = 0

    def add(self, text: str, method: str, *, page: int | None = None, section: str | None = None) -> bool:
        text = text.strip()
        if not text:
            return True
        # Separators belong to the fragment stream so offsets also reconstruct
        # the text exactly across boundaries inside a paragraph, row or page.
        if self.fragments:
            text = "\n\n" + text
        remaining = MAX_TEXT_CHARS - self.total_chars
        if len(self.fragments) == MAX_FRAGMENTS:
            self.diagnostics.append(f"Достигнут лимит фрагментов ({MAX_FRAGMENTS}).")
            return False
        if remaining > 0:
            self.fragments.append(TenderDocumentFragment(
                page=page, section=section, fragment=len(self.fragments) + 1,
                offset=self.total_chars, text=text[:remaining], method=method,
            ))
            self.total_chars += len(self.fragments[-1].text)
        if len(text) > remaining:
            self.diagnostics.append(f"Достигнут лимит текста ({MAX_TEXT_CHARS} символов).")
            return False
        return True


class _DocumentLimit(ValueError):
    pass


def _pdf_has_raster(resources, visited: set[int]) -> bool:
    if resources is None:
        return False
    resources = resources.get_object()
    if id(resources) in visited:
        return False
    visited.add(id(resources))
    xobjects = resources.get("/XObject")
    if xobjects is None:
        return False
    for reference in xobjects.get_object().values():
        obj = reference.get_object()
        subtype = obj.get("/Subtype")
        if subtype == "/Image":
            width, height = int(obj.get("/Width", 0)), int(obj.get("/Height", 0))
            if width * height >= 60000:
                return True
        if subtype == "/Form" and _pdf_has_raster(obj.get("/Resources"), visited):
            return True
    return False


def _reliable_ocr_words(confidence_report: Path) -> bool:
    try:
        with confidence_report.open(encoding="utf-8", newline="") as stream:
            scores = [
                float(row["conf"]) for row in csv.DictReader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
                if row["level"] == "5" and any(character.isalnum() for character in (row.get("text") or ""))
            ]
    except (OSError, KeyError, TypeError, ValueError):
        return False
    return bool(scores) and all(score >= MIN_OCR_WORD_CONFIDENCE for score in scores)


def _recognize_pdf_page(source: Path, page: int) -> tuple[str, bool]:
    image = source.parent / f"page-{page}"
    raster, text, confidence = (image.with_suffix(suffix) for suffix in (".png", ".txt", ".tsv"))
    try:
        subprocess.run(
            ["pdftoppm", "-f", str(page), "-l", str(page), "-scale-to", "2400", "-gray", "-png", "-singlefile", str(source), str(image)],
            cwd=source.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2, check=True,
        )
        subprocess.run(
            ["tesseract", str(raster), str(image), "-l", "rus+eng", "-c", "tessedit_create_txt=1", "-c", "tessedit_create_tsv=1"],
            cwd=source.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4, check=True,
        )
        return text.read_text(encoding="utf-8").strip(), _reliable_ocr_words(confidence)
    finally:
        raster.unlink(missing_ok=True)
        text.unlink(missing_ok=True)
        confidence.unlink(missing_ok=True)


def _extract_pdf(content: bytes, extraction: _Extraction, directory: Path) -> None:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    source = directory / "source.pdf"
    source.write_bytes(content)
    reader = PdfReader(BytesIO(content))
    if reader.is_encrypted:
        extraction.diagnostics.append("PDF защищён паролем.")
        return
    page_count = len(reader.pages)
    if page_count > MAX_PDF_PAGES:
        extraction.diagnostics.append(f"Обработано до {MAX_PDF_PAGES} из {page_count} страниц PDF.")
    ocr_pages = 0
    for index in range(min(page_count, MAX_PDF_PAGES)):
        page_number = index + 1
        embedded = ""
        try:
            page = reader.pages[index]
            embedded = page.extract_text(extraction_mode="layout", layout_mode_strip_rotated=False).strip()
            raster = _pdf_has_raster(page.get("/Resources"), set())
        except (AttributeError, ValueError, TypeError, KeyError, OSError, PyPdfError, RecursionError):
            raster = True
        if not extraction.add(embedded, "embedded", page=page_number):
            break
        if not raster and any(character.isalnum() for character in embedded):
            continue
        if ocr_pages == MAX_OCR_PAGES:
            extraction.diagnostics.append(f"Страница {page_number}: достигнут лимит страниц OCR ({MAX_OCR_PAGES}).")
            continue
        ocr_pages += 1
        try:
            recognized, reliable = _recognize_pdf_page(source, page_number)
        except (OSError, UnicodeError, subprocess.SubprocessError):
            recognized, reliable = "", False
        if not any(character.isalnum() for character in recognized):
            extraction.diagnostics.append(f"Страница {page_number}: OCR не смог извлечь текст.")
            continue
        if not reliable:
            extraction.diagnostics.append(f"Страница {page_number}: низкая уверенность OCR. Проверьте распознанный текст по оригиналу.")
        # Keep native clauses and remove only exact matches from OCR after
        # normalizing layout whitespace. The remaining scan evidence is independent.
        embedded_lines = {" ".join(line.split()) for line in embedded.splitlines() if line.strip()}
        extra_lines = [line for line in recognized.splitlines() if " ".join(line.split()) not in embedded_lines]
        if not extraction.add("\n".join(extra_lines), "ocr", page=page_number):
            break


def _word_paragraph(element) -> str:
    parts = []
    for node in element.iter():
        if node.tag == WORD_NS + "t":
            parts.append(node.text or "")
        elif node.tag == WORD_NS + "tab":
            parts.append("\t")
        elif node.tag in {WORD_NS + "br", WORD_NS + "cr"}:
            parts.append("\n")
    return "".join(parts)


def _word_children(element, tag):
    for child in element:
        if child.tag == WORD_NS + tag:
            yield child
        elif child.tag in WORD_WRAPPERS:
            yield from _word_children(child, tag)


def _word_blocks(element):
    for child in element:
        if child.tag == WORD_NS + "p":
            yield _word_paragraph(child)
        elif child.tag == WORD_NS + "tbl":
            for row in _word_children(child, "tr"):
                cells = ["\n".join(_word_blocks(cell)).strip() for cell in _word_children(row, "tc")]
                if any(cells):
                    yield " | ".join(cells)
        elif child.tag in WORD_BLOCK_WRAPPERS:
            yield from _word_blocks(child)


def _word_has_unreadable_inserts(root) -> bool:
    unreadable = {WORD_NS + "altChunk", WORD_NS + "object", WORD_NS + "pict"}
    for node in root.iter():
        if node.tag in unreadable:
            return True
        if node.tag == WORD_NS + "drawing" and next(node.iter(DRAWING_IMAGE), None) is not None:
            for extent in node.iter(DRAWING_EXTENT):
                # A large embedded image can contain a scan even when the
                # surrounding page contains readable Word text.
                if int(extent.get("cx", 0)) >= 1828800 and int(extent.get("cy", 0)) >= 914400:
                    return True
    return False


def _extract_docx(content: bytes, extraction: _Extraction) -> None:
    from defusedxml.ElementTree import fromstring

    with ZipFile(BytesIO(content)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_WORD_ENTRIES or sum(entry.file_size for entry in entries) > MAX_WORD_EXPANDED_BYTES:
            raise _DocumentLimit("DOCX превышает лимит распаковки.")
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)):
            raise ValueError("DOCX содержит дублирующиеся части.")
        supplements = sorted(name for name in names if WORD_SUPPLEMENTS.fullmatch(name))
        for name in ["word/document.xml", *supplements]:
            root = fromstring(archive.read(name))
            for block in _word_blocks(root):
                if not extraction.add(block, "docx", section=name):
                    return
            if _word_has_unreadable_inserts(root):
                extraction.diagnostics.append(f"В {name} есть вставки, которые требуют проверки в оригинале.")


def _extract_doc(content: bytes, extraction: _Extraction, directory: Path) -> None:
    source, output = directory / "source.doc", directory / "word.txt"
    source.write_bytes(content)
    try:
        with output.open("wb") as stream:
            subprocess.run(
                ["antiword", "-m", "UTF-8.txt", "-w", "0", str(source)],
                cwd=directory, stdout=stream, stderr=subprocess.DEVNULL, timeout=8, check=True,
            )
        with output.open(encoding="utf-8") as stream:
            text = stream.read(MAX_TEXT_CHARS + 1)
        if extraction.add(text, "doc") and len(text) > MAX_TEXT_CHARS:
            extraction.diagnostics.append(f"Достигнут лимит текста ({MAX_TEXT_CHARS} символов).")
    except FileNotFoundError:
        extraction.diagnostics.append("Чтение DOC недоступно: в среде отсутствует antiword.")
    except (OSError, UnicodeError, subprocess.SubprocessError):
        extraction.diagnostics.append("Не удалось прочитать DOC с помощью antiword.")


def _extract_original(content: bytes, document_format: str, directory: Path) -> dict:
    from defusedxml.common import DefusedXmlException
    from pypdf.errors import PyPdfError
    from xml.etree.ElementTree import ParseError

    extraction = _Extraction()
    try:
        if document_format == "pdf":
            _extract_pdf(content, extraction, directory)
        elif document_format == "docx":
            _extract_docx(content, extraction)
        else:
            _extract_doc(content, extraction, directory)
    except _DocumentLimit as exc:
        return {"status": "oversized", "diagnostics": [str(exc)]}
    except (BadZipFile, DefusedXmlException, KeyError, OSError, ParseError, PyPdfError, RecursionError, RuntimeError, ValueError):
        extraction.diagnostics.append("Не удалось разобрать файл. Проверьте оригинал документа.")
    if not extraction.fragments and not extraction.diagnostics:
        extraction.diagnostics.append("В оригинале не удалось найти читаемый текст.")
    status = "complete"
    if not extraction.fragments:
        status = "unreadable"
    elif extraction.diagnostics:
        status = "partial"
    return {
        "status": status, "diagnostics": extraction.diagnostics, "total_chars": extraction.total_chars,
        "fragments": [fragment.model_dump() for fragment in extraction.fragments],
    }


def _worker(document_format: str, directory: Path) -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (36, 38))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
    content = sys.stdin.buffer.read(MAX_ORIGINAL_BYTES + 1)
    if len(content) > MAX_ORIGINAL_BYTES:
        result = {"status": "oversized", "diagnostics": ["Оригинал превышает лимит размера файла."]}
    else:
        result = _extract_original(content, document_format, directory)
    sys.stdout.write(json.dumps(result, ensure_ascii=True))


async def _extract_in_worker(content: bytes, document_format: str) -> dict:
    # The parent owns cleanup even if it has to kill the parser mid-OCR.
    with tempfile.TemporaryDirectory(prefix="tender-document-") as temporary:
        worker = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "services.tender_document_reader", document_format, temporary,
            cwd=Path(__file__).resolve().parents[1],
            env={"PATH": os.defpath + os.pathsep + os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8", "OMP_THREAD_LIMIT": "1"},
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            output, _ = await asyncio.wait_for(worker.communicate(content), timeout=MAX_PARSER_SECONDS)
        except (TimeoutError, asyncio.CancelledError):
            try:
                os.killpg(worker.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await worker.wait()
            raise
    if worker.returncode:
        return {"status": "unreadable", "diagnostics": ["Чтение остановлено из-за ошибки или лимита обработки."]}
    return json.loads(output)


def _format_for(filename: str, mime_type: str) -> str | None:
    suffix = Path(filename.lower()).suffix
    if mime_type == "application/pdf" or suffix == ".pdf":
        return "pdf"
    if mime_type == WORD_MIME or suffix == ".docx":
        return "docx"
    if mime_type == "application/msword" or suffix == ".doc":
        return "doc"
    return None


async def _read_saved_original(
    session: AsyncSession, scope: TenantScope, *, order_id: int, document_id: str, source_reference: str | None,
) -> tuple[bytes, str, str, int] | None:
    from sqlmodel import select

    from core.config import settings
    from models import OrderAttachmentLink, ServiceAttachment
    from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService, SourceDocumentTooLarge, _source_identity
    from services.private_attachment_storage_service import PrivateAttachmentTooLarge, get_private_attachment_storage

    order = await BelzakupkiEnrichmentService._order(session, order_id, scope)
    if source_reference is None:
        source, external_id = _source_identity(order)
    else:
        from services.tender_source_reference import resolve_source_reference

        source, external_id = resolve_source_reference(order, source_reference)
    meta = ServiceAttachment.source_meta
    attachment = await session.scalar(
        select(ServiceAttachment)
        .join(OrderAttachmentLink, OrderAttachmentLink.attachment_id == ServiceAttachment.id)
        .where(
            OrderAttachmentLink.order_id == order_id,
            OrderAttachmentLink.archived_at.is_(None),
            ServiceAttachment.archived_at.is_(None),
            ServiceAttachment.source == "belzakupki",
            meta["purpose"].as_string() == "tender_original",
            meta["source"].as_string() == source,
            meta["external_id"].as_string() == external_id,
            meta["belzakupki_document_id"].as_string() == document_id,
        ).order_by(ServiceAttachment.id.desc()).limit(1)
    )
    if attachment is None or not attachment.content_hash or not attachment.storage_key:
        return None
    limit = min(MAX_ORIGINAL_BYTES, int(settings.SERVICE_ATTACHMENT_MAX_SIZE_BYTES))
    if attachment.size_bytes > limit:
        raise SourceDocumentTooLarge("Saved document exceeds the read limit")
    try:
        storage = get_private_attachment_storage(attachment.storage_provider)
        async with asyncio.timeout(10):
            content = await storage.read_bounded(attachment.storage_key, limit)
    except PrivateAttachmentTooLarge as exc:
        raise SourceDocumentTooLarge("Saved document exceeds the read limit") from exc
    except (OSError, RuntimeError, ValueError):
        return None
    if len(content) != attachment.size_bytes or hashlib.sha256(content).hexdigest() != attachment.content_hash:
        return None
    return content, attachment.original_filename, attachment.mime_type, attachment.id


async def load_tender_document(
    session: AsyncSession, scope: TenantScope, *, order_id: int, document_id: str, source_reference: str | None = None,
) -> TenderDocumentReadResult:
    from services.belzakupki_enrichment_service import (
        BelzakupkiEnrichmentService, SourceDocumentInventoryUnavailable, SourceDocumentNotFound, SourceDocumentTooLarge,
    )

    identity = {"order_id": order_id, "document_id": document_id, "source_reference": source_reference}
    reference_options = {} if source_reference is None else {"source_reference": source_reference}
    try:
        async with asyncio.timeout(3):
            await _parser_slots.acquire()
    except TimeoutError:
        return TenderDocumentReadResult(
            **identity, status="unavailable", diagnostics=["Все обработчики документов заняты. Повторите запрос позже."],
        )
    try:
        try:
            try:
                content, filename, mime_type = await BelzakupkiEnrichmentService.document(
                    session, order_id=order_id, document_id=document_id, scope=scope, max_bytes=MAX_ORIGINAL_BYTES, **reference_options,
                )
                identity["origin"] = "source"
            except (SourceDocumentInventoryUnavailable, SourceDocumentNotFound, httpx.HTTPError, RuntimeError):
                saved = await _read_saved_original(session, scope, **identity)
                if saved is None:
                    return TenderDocumentReadResult(
                        **identity, status="unavailable", diagnostics=["Оригинал недоступен через источник закупки."]
                    )
                content, filename, mime_type, attachment_id = saved
                identity.update(origin="saved_original", attachment_id=attachment_id)
        except SourceDocumentTooLarge:
            return TenderDocumentReadResult(
                **identity, status="oversized", diagnostics=["Ответ источника превышает лимит размера."],
            )
        identity.update(filename=filename, mime_type=mime_type, sha256=hashlib.sha256(content).hexdigest())
        document_format = _format_for(filename, mime_type)
        if not document_format:
            return TenderDocumentReadResult(
                **identity, status="unsupported", diagnostics=["Для чтения доступны PDF, DOC и DOCX."],
            )
        try:
            extraction = await _extract_in_worker(content, document_format)
        except (OSError, TimeoutError, UnicodeError, json.JSONDecodeError):
            extraction = {"status": "unreadable", "diagnostics": ["Чтение остановлено из-за ошибки или лимита времени."]}
        return TenderDocumentReadResult(**identity, **extraction)
    finally:
        _parser_slots.release()


async def read_tender_document(
    session: AsyncSession, scope: TenantScope, inputs: TenderDocumentReadInput,
) -> TenderDocumentReadResult:
    result = await load_tender_document(
        session, scope, order_id=inputs.order_id, document_id=inputs.document_id, source_reference=inputs.source_reference,
    )
    if inputs.sha256 and result.sha256 and result.sha256 != inputs.sha256:
        raise ValueError("Оригинал изменился. Начните чтение документа с начала.")
    start, end = inputs.offset, min(inputs.offset + inputs.limit, result.total_chars)
    if start > result.total_chars and result.sha256:
        raise ValueError("Смещение выходит за пределы извлечённого текста.")
    fragments = []
    for fragment in result.fragments:
        left, right = max(start, fragment.offset), min(end, fragment.offset + len(fragment.text))
        if left < right:
            if len(fragments) == MAX_WINDOW_FRAGMENTS:
                end = left
                break
            fragments.append(fragment.model_copy(update={
                "offset": left, "text": fragment.text[left - fragment.offset:right - fragment.offset],
            }))
    return result.model_copy(update={
        "fragments": fragments, "offset": start, "next_offset": end if end < result.total_chars else None,
    })


if __name__ == "__main__":
    _worker(sys.argv[1], Path(sys.argv[2]))
