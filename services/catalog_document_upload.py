"""Bounded PDF/DOCX uploads to the catalog's public reference namespace."""

import asyncio
from pathlib import PurePath

from fastapi import HTTPException, UploadFile

from schemas_catalog_documents import CatalogDocumentUploadResponse
from services.document_upload_validation import validate_pdf_or_docx
from services.general_media_storage_service import get_general_media_storage


MAX_CATALOG_DOCUMENT_BYTES = 25 * 1024 * 1024


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
        await asyncio.to_thread(validate_pdf_or_docx, content, extension)
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
