import pytest

from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService


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
