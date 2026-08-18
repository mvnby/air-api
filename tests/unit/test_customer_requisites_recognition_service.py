import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import CustomerRequisitesRecognition
from models.tenancy import TenantScope
from services.customer_requisites_recognition_service import (
    CustomerRequisitesRecognitionService,
    OcrProviderError,
)


TEST_TENANT_SCOPE = TenantScope(
    tenant_id=1,
    storefront_id=1,
    is_system=True,
)


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'requisites.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def test_normalize_vitebsk_landline_from_context():
    phone = CustomerRequisitesRecognitionService.normalize_phone(
        "69-73-29",
        context="211301 Витебская область, Витебский район, г. Витебск",
    )

    assert phone == "+375212697329"


def test_normalize_unknown_landline_returns_none():
    assert CustomerRequisitesRecognitionService.normalize_phone("69-73-29", context="") is None


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (400, "invalid_argument", False),
        (401, "credentials_rejected", False),
        (403, "credentials_rejected", False),
        (429, "rate_limited", True),
        (500, "upstream_error", True),
        (503, "upstream_error", True),
    ],
)
def test_google_vision_http_error_has_typed_retry_contract(
    status,
    code,
    retryable,
):
    error = HttpError(
        Response({"status": str(status), "reason": "test"}),
        b'{"error":{"message":"provider detail"}}',
    )

    mapped = CustomerRequisitesRecognitionService._vision_http_error(error)

    assert mapped.status == status
    assert mapped.code == code
    assert mapped.retryable is retryable
    assert "provider detail" not in str(mapped)


@pytest.mark.parametrize(
    ("rpc_status", "status", "code", "retryable"),
    [
        ("INVALID_ARGUMENT", 400, "invalid_argument", False),
        ("FAILED_PRECONDITION", 400, "failed_precondition", False),
        ("UNAUTHENTICATED", 401, "credentials_rejected", False),
        ("PERMISSION_DENIED", 403, "credentials_rejected", False),
        ("RESOURCE_EXHAUSTED", 429, "rate_limited", True),
        ("UNAVAILABLE", 503, "upstream_error", True),
        ("INTERNAL", 500, "upstream_error", True),
    ],
)
def test_google_vision_rpc_error_has_typed_retry_contract(
    rpc_status,
    status,
    code,
    retryable,
):
    mapped = CustomerRequisitesRecognitionService._vision_rpc_error(
        {"status": rpc_status, "code": status, "message": "secret"}
    )

    assert mapped.status == status
    assert mapped.code == code
    assert mapped.retryable is retryable


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (3, "invalid_argument", False),
        (7, "credentials_rejected", False),
        (9, "failed_precondition", False),
        (16, "credentials_rejected", False),
        (8, "rate_limited", True),
        (14, "upstream_error", True),
    ],
)
def test_google_vision_numeric_rpc_code_has_typed_retry_contract(
    status,
    code,
    retryable,
):
    mapped = CustomerRequisitesRecognitionService._vision_rpc_error(
        {"code": status, "message": "secret"}
    )

    assert mapped.status == status
    assert mapped.code == code
    assert mapped.retryable is retryable


@pytest.mark.parametrize(
    "error",
    [
        {},
        {"status": "FUTURE_CANONICAL_STATUS", "code": 14},
        {"status": [], "code": "not-a-number"},
    ],
)
def test_google_vision_malformed_rpc_status_fails_closed(error):
    mapped = CustomerRequisitesRecognitionService._vision_rpc_error(error)

    assert mapped.code == "unclassified_response"
    assert mapped.retryable is False


def test_google_vision_non_mapping_error_payload_fails_closed(monkeypatch):
    class Request:
        def execute(self):
            return {"responses": [{"error": "malformed"}]}

    class Images:
        def annotate(self, **_kwargs):
            return Request()

    class Vision:
        def images(self):
            return Images()

    monkeypatch.setattr(
        CustomerRequisitesRecognitionService,
        "_get_vision_client",
        lambda: Vision(),
    )

    with pytest.raises(OcrProviderError) as captured:
        CustomerRequisitesRecognitionService._vision_text_from_image_bytes_sync(
            b"image"
        )

    assert captured.value.code == "unclassified_response"
    assert captured.value.retryable is False


def test_google_vision_execute_network_failure_is_retryable(monkeypatch):
    class Request:
        def execute(self):
            raise OSError("network detail")

    class Images:
        def annotate(self, **_kwargs):
            return Request()

    class Vision:
        def images(self):
            return Images()

    monkeypatch.setattr(
        CustomerRequisitesRecognitionService,
        "_get_vision_client",
        lambda: Vision(),
    )

    with pytest.raises(OcrProviderError) as captured:
        CustomerRequisitesRecognitionService._vision_text_from_image_bytes_sync(
            b"image"
        )

    assert captured.value.code == "network_error"
    assert captured.value.retryable is True


def test_normalize_extracted_cleans_signer_basis_and_phone():
    extracted, flags = CustomerRequisitesRecognitionService._normalize_extracted(
        {
            "name": "УП «Витебскгазстрой» ОАО «Белгазстрой»",
            "inn": "300063995",
            "iban": "BY26BLBB30120300063995001001",
            "bic": "blbbby2x",
            "phone_raw": "69-73-29",
            "signer_position": "Директор",
            "signer_name": "Дмитриенко Сергея Александровича",
            "acting_basis": "действующий на основании Устава",
        },
        "г. Витебск",
    )

    assert extracted["signer_position"] == "директора"
    assert extracted["signer_name"] == "Дмитриенко Сергея Александровича"
    assert extracted["acting_basis"] == "Устава"
    assert extracted["phone"] == "+375212697329"
    assert extracted["bic"] == "BLBBBY2X"
    assert flags["is_valid"] is True


@pytest.mark.asyncio
async def test_recognize_rejects_too_large_file_before_ocr(monkeypatch):
    async def fail_extract(*args, **kwargs):
        raise AssertionError("OCR should not run for oversized files")

    monkeypatch.setattr(CustomerRequisitesRecognitionService, "extract_ocr_text", fail_extract)

    with pytest.raises(ValueError, match="Файл слишком большой"):
        await CustomerRequisitesRecognitionService.recognize_bytes(
            None,  # type: ignore[arg-type]
            content=b"x" * (CustomerRequisitesRecognitionService.MAX_FILE_SIZE_BYTES + 1),
            filename="req.pdf",
            mime_type="application/pdf",
            source="test",
            tenant_scope=TEST_TENANT_SCOPE,
        )


@pytest.mark.asyncio
async def test_extract_docx_requisites_text_without_ocr():
    document_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>ООО Климат</w:t></w:r></w:p>
        <w:p><w:r><w:t>УНП 123456789</w:t></w:r><w:r><w:t> IBAN BY00TEST</w:t></w:r></w:p>
      </w:body>
    </w:document>'''.encode()
    content = BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    text = await CustomerRequisitesRecognitionService.extract_ocr_text(
        content.getvalue(),
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="requisites.docx",
    )

    assert text == "ООО Климат\nУНП 123456789 IBAN BY00TEST"


@pytest.mark.asyncio
async def test_extract_legacy_doc_uses_bounded_antiword(monkeypatch):
    def fake_run(command, **kwargs):
        assert command[:3] == ["antiword", "-m", "UTF-8.txt"]
        assert kwargs["capture_output"] is True
        assert kwargs["timeout"] == 15
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="ООО Климат\nУНП 123456789".encode(),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    text = await CustomerRequisitesRecognitionService.extract_ocr_text(
        b"legacy-word",
        mime_type="application/msword",
        filename="requisites.doc",
    )

    assert text == "ООО Климат\nУНП 123456789"


@pytest.mark.asyncio
async def test_recognize_text_creates_recognition_without_file(sqlite_session, monkeypatch):
    async def fake_extract(raw_text):
        assert "МегаЕвроКлимат" in raw_text
        return {
            "name": "ЧУП «МегаЕвроКлимат»",
            "full_legal_name": "Частное унитарное предприятие «МегаЕвроКлимат»",
            "inn": "392053942",
            "legal_address": "г. Витебск, пр-т Победы, 15 ТРЦ «Мега», пав.127",
            "iban": "BY83BPSB30123542950119330000",
            "bic": "BPSBBY2X",
            "bank_name": "ОАО «Сбербанк»",
            "phone_raw": "8 (029) 722-03-63",
            "email": "7220363m@mail.ru",
        }

    monkeypatch.setattr(CustomerRequisitesRecognitionService, "extract_requisites", fake_extract)

    result = await CustomerRequisitesRecognitionService.recognize_text(
        sqlite_session,
        text="Частное унитарное предприятие «МегаЕвроКлимат»\nУНП 392053942\nР/с BY83 BPSB 3012 3542 9501 1933 0000\nBIC BPSBBY2X",
        source="telegram_text",
        tenant_scope=TEST_TENANT_SCOPE,
        telegram_user_id=7,
        telegram_chat_id=100,
        telegram_message_id=55,
    )

    assert result["source"] == "telegram_text"
    assert result["local_file_url"] is None
    assert result["extracted"]["inn"] == "392053942"
    assert result["extracted"]["iban"] == "BY83BPSB30123542950119330000"
    assert result["extracted"]["bic"] == "BPSBBY2X"
    assert result["validation_flags"]["is_valid"] is True

    stored = await sqlite_session.get(CustomerRequisitesRecognition, result["id"])
    assert stored is not None
    assert stored.tenant_id == TEST_TENANT_SCOPE.tenant_id
    assert stored.mime_type == "text/plain"
    assert stored.local_file_path is None
