"""Bounded PDF/DOCX uploads to the catalog's public reference namespace."""

import asyncio
from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile, ZipFile

from defusedxml.ElementTree import fromstring
from fastapi import HTTPException, UploadFile
from pypdf import PdfReader

from schemas_catalog_documents import CatalogDocumentUploadResponse
from services.general_media_storage_service import get_general_media_storage


MAX_CATALOG_DOCUMENT_BYTES = 25 * 1024 * 1024
_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_WORD_NAMESPACES = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
}
_DOCX_MAIN_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"


def _validate_pdf(content: bytes) -> None:
    if not content.startswith(b"%PDF-"):
        raise ValueError("Файл не является PDF.")
    try:
        reader = PdfReader(BytesIO(content), strict=True)
    except Exception as exc:
        raise ValueError("PDF повреждён или не может быть прочитан.") from exc
    if reader.is_encrypted:
        raise ValueError("Зашифрованные PDF не поддерживаются. Загрузите копию без пароля.")
    try:
        pages = list(reader.pages)
        for page in pages:
            # Materialize the real page tree and geometry, without extracting text.
            if page.get("/Type") != "/Page" or len(page.mediabox) != 4:
                raise ValueError("Invalid PDF page")
    except Exception as exc:
        raise ValueError("PDF повреждён или не содержит читаемых страниц.") from exc
    if not pages:
        raise ValueError("PDF не содержит страниц.")


def _validate_docx_xml(archive: ZipFile) -> None:
    content_types = fromstring(archive.read("[Content_Types].xml"), forbid_dtd=True)
    if any(
        "macroenabled" in item.get("ContentType", "").lower()
        or "vba" in item.get("ContentType", "").lower()
        for item in content_types
    ):
        raise ValueError("Документы с макросами не поддерживаются.")
    if content_types.tag != f"{{{_CONTENT_TYPES_NS}}}Types" or not any(
        item.get("PartName") == "/word/document.xml" and item.get("ContentType") == _DOCX_MAIN_TYPE
        for item in content_types.findall(f"{{{_CONTENT_TYPES_NS}}}Override")
    ):
        raise ValueError("DOCX не содержит основной документ Word.")
    document = fromstring(archive.read("word/document.xml"), forbid_dtd=True)
    if not any(
        document.tag == f"{{{namespace}}}document" and len(document.findall(f"{{{namespace}}}body")) == 1
        for namespace in _WORD_NAMESPACES
    ):
        raise ValueError("DOCX не содержит корректного тела документа Word.")


def _validate_content(content: bytes, extension: str) -> None:
    if extension == "pdf":
        _validate_pdf(content)
        return
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            if len(names) != len(archive.namelist()):
                raise ValueError("DOCX содержит повторяющиеся части.")
            if not {"[Content_Types].xml", "word/document.xml"}.issubset(names):
                raise ValueError("Файл не является DOCX.")
            if any(name.lower().endswith("vbaproject.bin") for name in names):
                raise ValueError("Документы с макросами не поддерживаются.")
            if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("Распакованный DOCX превышает 100 МБ.")
            _validate_docx_xml(archive)
    except ValueError:
        raise
    except BadZipFile as exc:
        raise ValueError("Файл не является DOCX.") from exc
    except Exception as exc:
        raise ValueError("DOCX повреждён или не может быть прочитан.") from exc


async def upload_catalog_document(file: UploadFile) -> CatalogDocumentUploadResponse:
    filename = PurePath((file.filename or "").replace("\\", "/")).name
    extension = PurePath(filename).suffix.lower().lstrip(".")
    if extension not in {"pdf", "docx"}:
        raise HTTPException(status_code=400, detail="Поддерживаются PDF и DOCX.")
    content = await file.read(MAX_CATALOG_DOCUMENT_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Файл пуст.")
    if len(content) > MAX_CATALOG_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Размер документа превышает 25 МБ.")
    try:
        await asyncio.to_thread(_validate_content, content, extension)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    storage = get_general_media_storage()
    stored = await storage.save_media(
        content=content,
        namespace="catalog-documents",
        variant_type="original",
        extension=extension,
        content_type="application/pdf" if extension == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    return CatalogDocumentUploadResponse(url=stored.url, title=PurePath(filename).stem[:250] or "Документ")
