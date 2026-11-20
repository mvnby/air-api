"""Verify bounded uploaded PDF and Word container structure."""

from io import BytesIO
from pathlib import PurePath
import shutil
import subprocess
import tempfile
import unicodedata
from zipfile import BadZipFile, ZipFile

from defusedxml.ElementTree import fromstring
from pypdf import PdfReader


_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_WORD_NAMESPACES = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
}
_DOCX_MAIN_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"

EXTERNAL_DOCUMENT_MAX_BYTES = 10 * 1024 * 1024
EXTERNAL_DOCUMENT_MIME_TYPES = {
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}
_OLE_HEADER = bytes.fromhex("D0CF11E0A1B11AE1")


class ExternalDocumentValidationUnavailable(RuntimeError):
    """The server could not validate the proposed file format."""


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


def validate_pdf_or_docx(content: bytes, extension: str) -> None:
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


def _validate_legacy_doc(content: bytes) -> None:
    if not content.startswith(_OLE_HEADER):
        raise ValueError("Файл не является DOC.")
    antiword = shutil.which("antiword")
    if not antiword:
        raise ExternalDocumentValidationUnavailable("Проверка DOC временно недоступна.")
    try:
        with tempfile.NamedTemporaryFile(suffix=".doc") as source:
            source.write(content)
            source.flush()
            completed = subprocess.run(
                [antiword, source.name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
    except OSError as exc:
        raise ExternalDocumentValidationUnavailable("Проверка DOC временно недоступна.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Не удалось вовремя проверить DOC.") from exc
    if completed.returncode != 0:
        raise ValueError("DOC повреждён или не может быть прочитан.")


def validate_external_document_size(content: bytes) -> None:
    if not isinstance(content, bytes) or not 0 < len(content) <= EXTERNAL_DOCUMENT_MAX_BYTES:
        raise ValueError("Размер файла должен быть от 1 байта до 10 МБ.")


def validate_external_document(
    content: bytes, filename: str, declared_mime_type: str, *, signed_copy: bool = False,
) -> tuple[str, str, str]:
    validate_external_document_size(content)
    name = PurePath(filename.replace("\\", "/")).name
    name = "".join("_" if unicodedata.category(char).startswith("C") else char for char in name).strip()
    if not name:
        if content.startswith(b"%PDF-"):
            name = "document.pdf"
        elif content.startswith(b"PK\x03\x04"):
            name = "document.docx"
        elif content.startswith(_OLE_HEADER):
            name = "document.doc"
    original_suffix = PurePath(name).suffix
    extension = original_suffix.lower().lstrip(".")
    mime_type = EXTERNAL_DOCUMENT_MIME_TYPES.get(extension)
    if not mime_type:
        raise ValueError("Поддерживаются DOC, DOCX и PDF.")
    if signed_copy and extension != "pdf":
        raise ValueError("Подписанный экземпляр должен быть PDF.")
    declared_type = declared_mime_type.lower().split(";", 1)[0].strip()
    if declared_type not in {"", "application/octet-stream", mime_type}:
        raise ValueError("Тип файла не соответствует расширению.")
    if extension == "doc":
        _validate_legacy_doc(content)
    else:
        validate_pdf_or_docx(content, extension)
    safe_name = f"{name[:-len(original_suffix)][:240]}{original_suffix}"
    return safe_name, mime_type, extension
