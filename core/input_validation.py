import re
from typing import Optional

PHONE_ERROR = "Телефон должен быть в формате +375XXXXXXXXX"
UNP_ERROR = "УНП должен содержать 9 цифр"
IBAN_ERROR = "IBAN должен быть валидным BY-счетом"
BIC_ERROR = "BIC должен содержать 8-11 латинских символов/цифр"

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_BIC_PATTERN = re.compile(r"^[A-Z0-9]{8,11}$")
_IBAN_BY_PATTERN = re.compile(r"^BY\d{2}[A-Z0-9]{24}$")


def clean_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def normalize_phone_digits(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return ""
    if digits.startswith("375") and len(digits) >= 12:
        return digits[:12]
    if digits.startswith("80") and len(digits) >= 11:
        return f"375{digits[2:11]}"
    if digits.startswith("0") and len(digits) >= 10:
        return f"375{digits[1:10]}"
    if len(digits) == 9:
        return f"375{digits}"
    return digits


def validate_optional_phone(value: Optional[str]) -> Optional[str]:
    cleaned = clean_optional(value)
    if not cleaned:
        return None
    normalized = normalize_phone_digits(cleaned)
    if len(normalized) != 12 or not normalized.startswith("375"):
        raise ValueError(PHONE_ERROR)
    return cleaned


def validate_required_phone(value: str) -> str:
    cleaned = clean_optional(value)
    if not cleaned:
        raise ValueError(PHONE_ERROR)
    normalized = normalize_phone_digits(cleaned)
    if len(normalized) != 12 or not normalized.startswith("375"):
        raise ValueError(PHONE_ERROR)
    return cleaned


def validate_optional_email(value: Optional[str]) -> Optional[str]:
    cleaned = clean_optional(value)
    if not cleaned:
        return None
    email = cleaned.lower()
    if not _EMAIL_PATTERN.match(email):
        raise ValueError("Некорректный email")
    return email


def normalize_unp(value: str) -> str:
    return re.sub(r"\D", "", value or "")[:9]


def validate_optional_unp(value: Optional[str]) -> Optional[str]:
    cleaned = clean_optional(value)
    if not cleaned:
        return None
    normalized = normalize_unp(cleaned)
    if len(normalized) != 9:
        raise ValueError(UNP_ERROR)
    return normalized


def normalize_iban(value: str) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def validate_optional_iban(value: Optional[str]) -> Optional[str]:
    cleaned = clean_optional(value)
    if not cleaned:
        return None
    iban = normalize_iban(cleaned)
    if not _IBAN_BY_PATTERN.match(iban):
        raise ValueError(IBAN_ERROR)
    return iban


def validate_optional_bic(value: Optional[str]) -> Optional[str]:
    cleaned = clean_optional(value)
    if not cleaned:
        return None
    bic = cleaned.replace(" ", "").upper()
    if not _BIC_PATTERN.match(bic):
        raise ValueError(BIC_ERROR)
    return bic
