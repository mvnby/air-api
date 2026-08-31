import pytest

from core.input_validation import (
    validate_optional_bic,
    validate_optional_email,
    validate_optional_iban,
    validate_optional_phone,
    validate_optional_unp,
    validate_required_phone,
)


def test_validate_required_phone_accepts_belarus_formats():
    assert validate_required_phone("+375291112233") == "+375291112233"
    assert validate_required_phone("+375 (29) 111-22-33") == "+375 (29) 111-22-33"


def test_validate_required_phone_accepts_international_formats():
    assert validate_required_phone("+7 (916) 111-22-33") == "+7 (916) 111-22-33"
    assert validate_required_phone("+77 12 345 67 89") == "+77 12 345 67 89"
    assert validate_required_phone("89161112233") == "89161112233"


def test_validate_required_phone_rejects_invalid():
    with pytest.raises(ValueError):
        validate_required_phone("+12")
    with pytest.raises(ValueError):
        validate_required_phone("+7 test")


def test_validate_optional_email_normalizes_and_rejects():
    assert validate_optional_email("  TEST@Example.com ") == "test@example.com"
    assert validate_optional_email("   ") is None
    with pytest.raises(ValueError):
        validate_optional_email("not-an-email")


def test_validate_optional_unp_accepts_9_digits_only():
    assert validate_optional_unp(" 300149331 ") == "300149331"
    with pytest.raises(ValueError):
        validate_optional_unp("12345")


def test_validate_optional_iban_accepts_valid_by_iban():
    assert validate_optional_iban("BY13ALFA30122644440010270000") == "BY13ALFA30122644440010270000"
    assert validate_optional_iban("BY57ОLMP30125000210500000933") == "BY57OLMP30125000210500000933"
    with pytest.raises(ValueError):
        validate_optional_iban("DE89370400440532013000")
    with pytest.raises(ValueError):
        validate_optional_iban("BY13ALFA3012264444001027000")


def test_validate_optional_bic():
    assert validate_optional_bic("alfaby2x") == "ALFABY2X"
    with pytest.raises(ValueError):
        validate_optional_bic("bad")


def test_validate_optional_phone_allows_empty():
    assert validate_optional_phone(None) is None
    assert validate_optional_phone("   ") is None
