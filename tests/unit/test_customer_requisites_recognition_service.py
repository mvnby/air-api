from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import CustomerRequisitesRecognition
from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService


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
        )


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
    assert stored.mime_type == "text/plain"
    assert stored.local_file_path is None
