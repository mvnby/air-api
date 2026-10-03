import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import Customer, CustomerContact, CustomerContactHistory, CustomerRequisitesRecognition, CustomerType
from models.tenancy import TenantScope
from services.customer_requisites_recognition_service import (
    CustomerRequisitesRecognitionService,
    OcrProviderError,
)
from services.customer_requisites_confirmation_service import CustomerRequisitesConflictError


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
    ("extracted", "raw_text", "expected_type", "expected_signing_mode"),
    [
        (
            {"name": "ООО Тест"},
            "",
            "company",
            "statutory_body",
        ),
        (
            {
                "name": "ИП Иванов Иван Иванович",
                "inn": "391823267",
            },
            "",
            "individual_entrepreneur",
            "self",
        ),
        (
            {"name": "Иванов Иван Иванович", "inn": "391823267"},
            "",
            "individual_entrepreneur",
            "self",
        ),
        (
            {"name": "Иванов Иван Иванович"},
            "",
            "individual",
            "self",
        ),
        (
            {"name": "Иванов Иван", "inn": "391823267"},
            "Индивидуальный предприниматель Иванов Иван",
            "individual_entrepreneur",
            "self",
        ),
        (
            {"name": "Иванов Иван Иванович", "inn": "123456789"},
            "ООО «Ромашка» УНП 123456789 директор Иванов Иван Иванович",
            "company",
            "statutory_body",
        ),
        (
            {"name": "Иванов Иван Иванович", "inn": "391823267"},
            "Иванов Иван Иванович УНП 391823267 банк ОАО «Белинвестбанк»",
            "individual_entrepreneur",
            "self",
        ),
        (
            {"name": "МегаЕвроКлимат", "inn": "392053942"},
            "",
            "company",
            "statutory_body",
        ),
    ],
)
def test_customer_payload_infers_party_type_and_signing_mode(
    extracted,
    raw_text,
    expected_type,
    expected_signing_mode,
) -> None:
    payload = CustomerRequisitesRecognitionService._customer_payload(
        extracted,
        raw_text=raw_text,
    )

    assert payload["type"].value == expected_type
    assert payload["signing_mode"] == expected_signing_mode


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
    assert extracted["customer_type"] == "company"
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


@pytest.mark.asyncio
async def test_corrected_draft_creates_once_and_ignores_unselected_fields(sqlite_session, monkeypatch):
    async def fake_extract(_raw_text):
        return {"name": "ООО Новый", "inn": "300063995", "bank_name": "Старый банк", "iban": "invalid"}

    monkeypatch.setattr(CustomerRequisitesRecognitionService, "extract_requisites", fake_extract)
    recognized = await CustomerRequisitesRecognitionService.recognize_text(
        sqlite_session, text="ООО Новый УНП 300063995 реквизиты клиента", source="manager",
        tenant_scope=TEST_TENANT_SCOPE,
    )
    kwargs = dict(
        recognition_id=recognized["id"], action="create", customer_id=None,
        extracted={"name": "ООО Исправленное"},
        selected_fields=["name", "inn", "customer_type"],
        baseline=None, tenant_scope=TEST_TENANT_SCOPE,
    )
    first = await CustomerRequisitesRecognitionService.confirm(sqlite_session, **kwargs)
    second = await CustomerRequisitesRecognitionService.confirm(sqlite_session, **kwargs)
    assert second["customer"]["id"] == first["customer"]["id"]
    assert first["customer"]["name"] == "ООО Исправленное"
    assert first["customer"]["bank_name"] is None
    assert first["customer"]["full_legal_name"] is None
    assert first["customer"]["type"] == "company"


@pytest.mark.asyncio
async def test_update_selected_fields_checks_baseline_and_preserves_signing(sqlite_session, monkeypatch):
    existing = Customer(
        tenant_id=1, name="ООО Действующее", phone="", type=CustomerType.company,
        signing_mode="power_of_attorney", inn="300063995", bank_name="Старый банк",
        signer_position="председателя", acting_basis="Доверенности",
    )
    sqlite_session.add(existing)
    await sqlite_session.commit()
    await sqlite_session.refresh(existing)

    async def fake_extract(_raw_text):
        return {"name": "ООО Действующее", "inn": "300063995", "bank_name": "Новый банк"}

    monkeypatch.setattr(CustomerRequisitesRecognitionService, "extract_requisites", fake_extract)
    recognized = await CustomerRequisitesRecognitionService.recognize_text(
        sqlite_session, text="ООО Действующее УНП 300063995 реквизиты", source="manager",
        tenant_scope=TEST_TENANT_SCOPE,
    )
    kwargs = dict(
        recognition_id=recognized["id"], action="update", customer_id=existing.id,
        extracted={"bank_name": "Исправленный банк"}, selected_fields=["bank_name"],
        baseline={"bank_name": "Старый банк"}, tenant_scope=TEST_TENANT_SCOPE,
    )
    existing.bank_name = "Правка другого менеджера"
    await sqlite_session.commit()
    with pytest.raises(CustomerRequisitesConflictError):
        await CustomerRequisitesRecognitionService.confirm(sqlite_session, **kwargs)
    assert existing.bank_name == "Правка другого менеджера"

    kwargs["baseline"] = {"bank_name": "Правка другого менеджера"}
    confirmed = await CustomerRequisitesRecognitionService.confirm(sqlite_session, **kwargs)
    assert confirmed["customer"]["bank_name"] == "Исправленный банк"
    assert confirmed["customer"]["signing_mode"] == "power_of_attorney"
    assert confirmed["customer"]["signer_position"] == "председателя"
    assert confirmed["customer"]["acting_basis"] == "Доверенности"


@pytest.mark.asyncio
async def test_phone_match_does_not_implicitly_choose_update_target(sqlite_session, monkeypatch):
    existing = Customer(
        tenant_id=1, name="Другая компания", phone="+375291112233",
        type=CustomerType.company, signing_mode="statutory_body",
    )
    sqlite_session.add(existing)
    await sqlite_session.commit()

    async def fake_extract(_raw_text):
        return {"name": "ООО Новая", "phone": "+375291112233"}

    monkeypatch.setattr(CustomerRequisitesRecognitionService, "extract_requisites", fake_extract)
    recognized = await CustomerRequisitesRecognitionService.recognize_text(
        sqlite_session, text="ООО Новая телефон +375291112233 реквизиты", source="manager",
        tenant_scope=TEST_TENANT_SCOPE,
    )
    assert recognized["duplicate_customer"]["id"] == existing.id
    assert recognized["duplicate_customer"]["matched_fields"] == ["phone"]
    with pytest.raises(ValueError, match="Не выбран клиент"):
        await CustomerRequisitesRecognitionService.confirm(
            sqlite_session, recognition_id=recognized["id"], action="update",
            tenant_scope=TEST_TENANT_SCOPE,
        )


@pytest.mark.asyncio
async def test_requisites_phone_update_keeps_primary_contact_in_sync(sqlite_session, monkeypatch):
    existing = Customer(
        tenant_id=1, name="ООО Контакт", phone="+375291112233",
        type=CustomerType.company, signing_mode="statutory_body",
    )
    sqlite_session.add(existing)
    await sqlite_session.flush()
    primary = CustomerContact(
        customer_id=existing.id, name="Основной", phone="+375291112233",
        is_primary=True, is_active=True,
    )
    sqlite_session.add(primary)
    await sqlite_session.commit()

    async def fake_extract(_raw_text):
        return {"name": "ООО Контакт", "phone": "+375291112244"}

    monkeypatch.setattr(CustomerRequisitesRecognitionService, "extract_requisites", fake_extract)
    recognized = await CustomerRequisitesRecognitionService.recognize_text(
        sqlite_session, text="ООО Контакт телефон +375291112244 реквизиты", source="manager",
        tenant_scope=TEST_TENANT_SCOPE,
    )
    await CustomerRequisitesRecognitionService.confirm(
        sqlite_session, recognition_id=recognized["id"], action="update",
        customer_id=existing.id, extracted={"phone": "+375291112255"},
        selected_fields=["phone"], baseline={"phone": "+375291112233"},
        tenant_scope=TEST_TENANT_SCOPE,
    )
    await sqlite_session.refresh(primary)
    await sqlite_session.refresh(existing)
    assert existing.phone == "+375291112255"
    assert primary.phone == "+375291112255"
    history = (await sqlite_session.execute(select(CustomerContactHistory))).scalars().all()
    assert any(row.field_name == "phone" and row.new_value == "+375291112255" for row in history)


@pytest.mark.asyncio
async def test_selected_empty_strings_clear_optional_fields_but_not_name(sqlite_session, monkeypatch):
    existing = Customer(
        tenant_id=1, name="ООО Клиент", full_legal_name="ООО Полное",
        email="old@example.test", phone="+375291112233",
        type=CustomerType.company, signing_mode="statutory_body",
    )
    sqlite_session.add(existing)
    await sqlite_session.commit()
    await sqlite_session.refresh(existing)

    async def fake_extract(_raw_text):
        return {"name": "ООО Клиент", "full_legal_name": "ООО Полное", "email": "old@example.test"}

    monkeypatch.setattr(CustomerRequisitesRecognitionService, "extract_requisites", fake_extract)
    recognized = await CustomerRequisitesRecognitionService.recognize_text(
        sqlite_session, text="ООО Клиент, реквизиты и контактные данные", source="manager",
        tenant_scope=TEST_TENANT_SCOPE,
    )
    with pytest.raises(ValueError, match="name"):
        await CustomerRequisitesRecognitionService.confirm(
            sqlite_session, recognition_id=recognized["id"], action="update",
            customer_id=existing.id, extracted={"name": ""}, selected_fields=["name"],
            baseline={"name": "ООО Клиент"}, tenant_scope=TEST_TENANT_SCOPE,
        )

    result = await CustomerRequisitesRecognitionService.confirm(
        sqlite_session, recognition_id=recognized["id"], action="update",
        customer_id=existing.id,
        extracted={"full_legal_name": "", "email": "", "phone": ""},
        selected_fields=["full_legal_name", "email", "phone"],
        baseline={"full_legal_name": "ООО Полное", "email": "old@example.test", "phone": "+375291112233"},
        tenant_scope=TEST_TENANT_SCOPE,
    )
    assert result["customer"]["name"] == "ООО Клиент"
    assert result["customer"]["full_legal_name"] is None
    assert result["customer"]["email"] is None
    assert result["customer"]["phone"] == ""


@pytest.mark.asyncio
async def test_explicit_party_type_change_keeps_signing_mode_valid(sqlite_session, monkeypatch):
    existing = Customer(
        tenant_id=1, name="Иванов Иван Иванович", phone="",
        type=CustomerType.individual, signing_mode="self",
    )
    sqlite_session.add(existing)
    await sqlite_session.commit()
    await sqlite_session.refresh(existing)

    async def fake_extract(_raw_text):
        return {"name": "ООО Клиент", "customer_type": "company"}

    monkeypatch.setattr(CustomerRequisitesRecognitionService, "extract_requisites", fake_extract)
    recognized = await CustomerRequisitesRecognitionService.recognize_text(
        sqlite_session, text="ООО Клиент, юридические реквизиты", source="manager",
        tenant_scope=TEST_TENANT_SCOPE,
    )
    result = await CustomerRequisitesRecognitionService.confirm(
        sqlite_session, recognition_id=recognized["id"], action="update",
        customer_id=existing.id, extracted={"customer_type": "company"},
        selected_fields=["customer_type"], baseline={"customer_type": "individual"},
        tenant_scope=TEST_TENANT_SCOPE,
    )
    assert result["customer"]["type"] == "company"
    assert result["customer"]["signing_mode"] == "statutory_body"


def test_pdf_over_five_pages_is_rejected_instead_of_partially_read():
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(6):
        writer.add_blank_page(width=595, height=842)
    output = BytesIO()
    writer.write(output)

    with pytest.raises(ValueError, match="больше 5 страниц"):
        CustomerRequisitesRecognitionService._extract_pdf_text(output.getvalue())
