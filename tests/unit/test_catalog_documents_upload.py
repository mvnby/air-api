from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zipfile import ZipFile
from threading import get_ident

import pytest
from fastapi import HTTPException, UploadFile
from pypdf import PdfWriter

from services import catalog_document_upload
from services.general_media_storage_service import LocalGeneralMediaStorage


def _pdf(*, password=None, with_page=True):
    writer = PdfWriter()
    if with_page:
        writer.add_blank_page(width=595, height=842)
    if password:
        writer.encrypt(password)
    content = BytesIO()
    writer.write(content)
    return content.getvalue()


def _docx(*, content_types=None, document=None, macro=False):
    content = BytesIO()
    with ZipFile(content, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types if content_types is not None else (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>'
        ))
        archive.writestr("word/document.xml", document if document is not None else (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>'
        ))
        if macro:
            archive.writestr("word/vbaProject.bin", b"macro")
    return content.getvalue()


@pytest.mark.asyncio
async def test_local_catalog_files_are_written_outside_async_event_loop(tmp_path, monkeypatch):
    storage = LocalGeneralMediaStorage(base_dir=tmp_path)
    write_threads = []
    original_write = storage._save_local_content
    def record_write(path, content):
        write_threads.append(get_ident())
        original_write(path, content)
    monkeypatch.setattr(storage, "_save_local_content", record_write)
    result = await storage.save_media(content=b"%PDF-1.7", namespace="catalog-documents", variant_type="original", extension="pdf")
    assert write_threads and write_threads[0] != get_ident()
    assert await storage.read_media(result.path) == b"%PDF-1.7"


@pytest.mark.asyncio
async def test_public_pdf_uses_dedicated_catalog_storage(monkeypatch):
    storage = SimpleNamespace(save_media=AsyncMock(return_value=SimpleNamespace(url="https://cdn.mvn.by/catalog-documents/original/file.pdf")))
    monkeypatch.setattr(catalog_document_upload, "get_general_media_storage", lambda: storage)
    result = await catalog_document_upload.upload_catalog_document(UploadFile(filename="Manual.pdf", file=BytesIO(_pdf())))
    assert result.title == "Manual"
    assert result.url.endswith("file.pdf")
    assert storage.save_media.await_args.kwargs["namespace"] == "catalog-documents"
    assert storage.save_media.await_args.kwargs["content_type"] == "application/pdf"


@pytest.mark.asyncio
async def test_upload_accepts_docx_and_rejects_macros(monkeypatch):
    storage = SimpleNamespace(save_media=AsyncMock(return_value=SimpleNamespace(url="/media/catalog-documents/original/file.docx")))
    monkeypatch.setattr(catalog_document_upload, "get_general_media_storage", lambda: storage)
    result = await catalog_document_upload.upload_catalog_document(UploadFile(filename="Reference.docx", file=BytesIO(_docx())))
    assert result.title == "Reference"
    with pytest.raises(HTTPException) as error:
        await catalog_document_upload.upload_catalog_document(UploadFile(filename="Reference.docx", file=BytesIO(_docx(macro=True))))
    assert error.value.status_code == 400
    assert storage.save_media.await_count == 1


@pytest.mark.parametrize("name,content,status", [
    ("Reference.doc", b"document", 400),
    ("Reference.pdf", b"<html>not a PDF</html>", 400),
    ("Reference.docx", b"not a ZIP archive", 400),
    ("Reference.pdf", b"", 400),
    ("Reference.pdf", b"%PDF-" + b"x" * 30, 413),
])
@pytest.mark.asyncio
async def test_upload_rejects_invalid_or_oversized_content_before_storage(name, content, status, monkeypatch):
    monkeypatch.setattr(catalog_document_upload, "MAX_CATALOG_DOCUMENT_BYTES", 25)
    storage = AsyncMock()
    monkeypatch.setattr(catalog_document_upload, "get_general_media_storage", storage)
    with pytest.raises(HTTPException) as error:
        await catalog_document_upload.upload_catalog_document(UploadFile(filename=name, file=BytesIO(content)))
    assert error.value.status_code == status
    storage.assert_not_called()


@pytest.mark.parametrize("name,content", [
    ("Corrupt.pdf", b"%PDF-1.7\nnot a PDF object graph"),
    ("Truncated.pdf", _pdf()[:-20]),
    ("Encrypted.pdf", _pdf(password="secret")),
    ("Empty.pdf", _pdf(with_page=False)),
    ("Broken.docx", _docx(document="<w:broken")),
    ("WrongRoot.docx", _docx(document="<document><body/></document>")),
    ("NoBody.docx", _docx(document='<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')),
    ("WrongType.docx", _docx(content_types="<Types/>")),
    ("DeclaredMacro.docx", _docx(content_types=(
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/>'
        '</Types>'
    ))),
    ("Entity.docx", _docx(document='<!DOCTYPE word [<!ENTITY file SYSTEM "file:///etc/passwd">]><word>&file;</word>')),
], ids=lambda value: value if isinstance(value, str) else "content")
@pytest.mark.asyncio
async def test_upload_parses_real_pdf_pages_and_safe_docx_xml_before_storage(name, content, monkeypatch):
    storage = AsyncMock()
    monkeypatch.setattr(catalog_document_upload, "get_general_media_storage", storage)
    with pytest.raises(HTTPException) as error:
        await catalog_document_upload.upload_catalog_document(UploadFile(filename=name, file=BytesIO(content)))
    assert error.value.status_code == 400
    storage.assert_not_called()
