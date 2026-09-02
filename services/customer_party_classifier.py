"""Deterministic customer party classification for recognized requisites."""

import re
from typing import Any, Mapping

from models import CustomerType


_ENTREPRENEUR_PATTERN = re.compile(
    r"(?:\bип\b|"
    r"\bиндивидуальн\w*\s+предпринимател\w*\b|"
    r"\bіндывідуальн\w*\s+прадпрымальнік\w*\b)",
    flags=re.IGNORECASE,
)

_COMPANY_PATTERN = re.compile(
    r"(?:"
    r"\b(?:ооо|одо|оао|зао|пао|ао|иооо|уп|чуп|пуп|руп|куп|гуп|"
    r"таа|тда|аат|зат)\b|"
    r"\b(?:общество|таварыства)\s+с\s+"
    r"(?:ограниченной|дополнительной)\s+ответственностью\b|"
    r"\bтаварыства\s+з\s+(?:абмежаванай|дадатковай)\s+адказнасцю\b|"
    r"\b(?:открытое|закрытое|публичное)\s+акционерное\s+общество\b|"
    r"\b(?:адкрытае|закрытае)\s+акцыянернае\s+таварыства\b|"
    r"\b(?:частное|производственное|республиканское|коммунальное|"
    r"государственное)\s+"
    r"унитарное\s+предприятие\b|"
    r"\b(?:прыватнае|вытворчае|рэспубліканскае|камунальнае|"
    r"дзяржаўнае)\s+"
    r"унітарнае\s+прадпрыемства\b|"
    r"\b(?:производственный|потребительский)\s+кооператив\b|"
    r"\b(?:крестьянское|фермерское)\s+хозяйство\b"
    r")",
    flags=re.IGNORECASE,
)

_CYRILLIC_NAME_TOKEN = re.compile(r"^[а-яёіў'’-]+$", flags=re.IGNORECASE)
_PATRONYMIC_SUFFIX = re.compile(
    r"(?:ович|евич|ич|инич|овна|евна|ична|авіч|евіч|овіч|аўна|еўна)$",
    flags=re.IGNORECASE,
)
_CUSTOMER_TYPE_VALUES = frozenset(item.value for item in CustomerType)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _looks_like_person_name(value: str) -> bool:
    tokens = [token.strip(".,;:()[]{}\"«»") for token in value.split()]
    tokens = [token for token in tokens if token]
    if len(tokens) not in {3, 4}:
        return False
    if not all(_CYRILLIC_NAME_TOKEN.fullmatch(token) for token in tokens):
        return False
    return any(_PATRONYMIC_SUFFIX.search(token) for token in tokens[1:])


def _raw_entity_header(raw_text: str) -> str:
    """Keep the party heading and exclude bank legal forms from classification."""

    return re.split(
        r"\b(?:унп|банк|iban|bic)\b|р\s*/\s*с|расч[её]тн\w*\s+сч[её]т",
        raw_text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]


def infer_customer_type_from_requisites(
    extracted: Mapping[str, Any],
    *,
    raw_text: str = "",
) -> CustomerType:
    """Infer the CRM party type without trusting the external AI to classify it."""

    stored_type = _text(extracted.get("customer_type")).lower()
    if stored_type in _CUSTOMER_TYPE_VALUES:
        return CustomerType(stored_type)

    name = _text(extracted.get("name"))
    full_legal_name = _text(extracted.get("full_legal_name"))
    identity = " ".join(dict.fromkeys(filter(None, (full_legal_name, name))))

    if _ENTREPRENEUR_PATTERN.search(identity):
        return CustomerType.individual_entrepreneur
    if _COMPANY_PATTERN.search(identity):
        return CustomerType.company

    # A requisites sheet sometimes contains only the entrepreneur's FIO in the
    # extracted name while the explicit ИП marker remains in the OCR text.
    if _ENTREPRENEUR_PATTERN.search(raw_text):
        return CustomerType.individual_entrepreneur
    if _COMPANY_PATTERN.search(_raw_entity_header(raw_text)):
        return CustomerType.company

    inn = _text(extracted.get("inn"))
    if inn and _looks_like_person_name(identity):
        return CustomerType.individual_entrepreneur
    if inn:
        return CustomerType.company

    return CustomerType.individual
