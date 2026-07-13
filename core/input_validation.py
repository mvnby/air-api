import re
from typing import Optional
from urllib.parse import unquote, urlsplit, urlunsplit

PHONE_ERROR = "Телефон должен быть в международном формате, например +375XXXXXXXXX или +7XXXXXXXXXX"
UNP_ERROR = "УНП должен содержать 9 цифр"
IBAN_ERROR = "IBAN должен быть валидным BY-счетом"
BIC_ERROR = "BIC должен содержать 8-11 латинских символов/цифр"
MANUAL_URL_ERROR = "Ссылка на инструкцию должна использовать HTTP(S) или локальный путь /media/"

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_PATTERN = re.compile(r"^\+?[\d\s().-]+$")
_BIC_PATTERN = re.compile(r"^[A-Z0-9]{8,11}$")
_IBAN_BY_PATTERN = re.compile(r"^BY\d{2}[A-Z0-9]{24}$")
_CONTROL_OR_SPACE_PATTERN = re.compile(r"[\x00-\x20\x7f]")
_PUBLIC_MANUAL_RELATIVE_PREFIXES = ("/media/",)


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


def is_valid_phone(value: str) -> bool:
    cleaned = clean_optional(value)
    if not cleaned or not _PHONE_PATTERN.match(cleaned):
        return False
    normalized = normalize_phone_digits(cleaned)
    return 7 <= len(normalized) <= 15


def validate_optional_phone(value: Optional[str]) -> Optional[str]:
    cleaned = clean_optional(value)
    if not cleaned:
        return None
    if not is_valid_phone(cleaned):
        raise ValueError(PHONE_ERROR)
    return cleaned


def validate_required_phone(value: str) -> str:
    cleaned = clean_optional(value)
    if not cleaned or not is_valid_phone(cleaned):
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


def validate_public_manual_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw or _CONTROL_OR_SPACE_PATTERN.search(raw) or "\\" in raw:
        raise ValueError(MANUAL_URL_ERROR)

    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme:
        if scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(MANUAL_URL_ERROR)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError(MANUAL_URL_ERROR)
        return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, ""))

    if parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        raise ValueError(MANUAL_URL_ERROR)
    if not parsed.path.startswith(_PUBLIC_MANUAL_RELATIVE_PREFIXES):
        raise ValueError(MANUAL_URL_ERROR)

    decoded_segments = [unquote(segment) for segment in parsed.path.split("/")]
    if any(
        segment in {".", ".."} or "/" in segment or "\\" in segment
        for segment in decoded_segments
    ):
        raise ValueError(MANUAL_URL_ERROR)

    return urlunsplit(("", "", parsed.path, parsed.query, ""))
