from __future__ import annotations

import re
from typing import Any


ORGANIZATION = "organization"
INDIVIDUAL_ENTREPRENEUR = "individual_entrepreneur"
INDIVIDUAL = "individual"

SELF = "self"
STATUTORY_BODY = "statutory_body"
POWER_OF_ATTORNEY = "power_of_attorney"


_INDIVIDUAL_ENTREPRENEUR_NAME_PATTERN = re.compile(
    r"(?:^|\s)(?:ип|индивидуальн\w*\s+предпринимател\w*)(?:\s|$)",
    re.IGNORECASE,
)
_ORGANIZATION_NAME_PATTERN = re.compile(
    r"(?:^|\s)(?:ооо|одо|оао|зао|чуп|руп|куп|гуп|уп|гу|"
    r"общество\s+с\s+(?:ограниченной|дополнительной)\s+ответственностью|"
    r"открытое\s+акционерное\s+общество|закрытое\s+акционерное\s+общество)"
    r"(?:\s|$)",
    re.IGNORECASE,
)


def customer_document_entity_type(
    value: Any,
    *,
    name: Any = None,
    full_legal_name: Any = None,
    inn: Any = None,
    legal_address: Any = None,
    bank_name: Any = None,
    iban: Any = None,
    bic: Any = None,
) -> str:
    """Resolve a document party type without mutating a legacy customer row.

    ``company`` and ``individual_entrepreneur`` are explicit, authoritative
    selections. Older CRM records may still contain the default ``individual``
    value despite a legal form in their name; that strong identity evidence wins
    over the stale default. Requisites only resolve an absent/invalid type, as
    an UNP or bank account alone may also belong to an entrepreneur.
    """

    normalized = getattr(value, "value", value)
    normalized = str(normalized or "").strip().lower()
    if normalized == "company":
        return ORGANIZATION
    if normalized == INDIVIDUAL_ENTREPRENEUR:
        return INDIVIDUAL_ENTREPRENEUR

    party_names = " ".join(
        str(candidate or "").strip()
        for candidate in (full_legal_name, name)
        if str(candidate or "").strip()
    )
    if _INDIVIDUAL_ENTREPRENEUR_NAME_PATTERN.search(party_names):
        return INDIVIDUAL_ENTREPRENEUR
    if _ORGANIZATION_NAME_PATTERN.search(party_names):
        return ORGANIZATION

    if normalized == INDIVIDUAL:
        return INDIVIDUAL

    business_requisites = (inn, legal_address, bank_name, iban, bic)
    if sum(bool(str(item or "").strip()) for item in business_requisites) >= 2:
        return ORGANIZATION
    return INDIVIDUAL


def default_signing_mode(entity_type: str) -> str:
    return STATUTORY_BODY if entity_type == ORGANIZATION else SELF


def normalize_signing_mode(entity_type: str, value: Any) -> str:
    normalized = str(value or "").strip().lower()
    allowed = {
        ORGANIZATION: {STATUTORY_BODY, POWER_OF_ATTORNEY},
        INDIVIDUAL_ENTREPRENEUR: {SELF, POWER_OF_ATTORNEY},
        INDIVIDUAL: {SELF, POWER_OF_ATTORNEY},
    }
    if normalized not in allowed.get(entity_type, set()):
        return default_signing_mode(entity_type)
    return normalized


def entity_type_label(entity_type: str) -> str:
    return {
        ORGANIZATION: "Организация",
        INDIVIDUAL_ENTREPRENEUR: "Индивидуальный предприниматель",
        INDIVIDUAL: "Физическое лицо",
    }.get(entity_type, "Физическое лицо")


def party_conditions(
    prefix: str,
    *,
    entity_type: str,
    signing_mode: str,
) -> dict[str, bool]:
    """Return server-owned condition flags; templates never evaluate expressions."""

    is_organization = entity_type == ORGANIZATION
    is_ip = entity_type == INDIVIDUAL_ENTREPRENEUR
    is_individual = entity_type == INDIVIDUAL
    signs_self = signing_mode == SELF
    signs_as_body = signing_mode == STATUTORY_BODY
    signs_by_poa = signing_mode == POWER_OF_ATTORNEY
    return {
        f"{prefix}.is_organization": is_organization,
        f"{prefix}.is_individual_entrepreneur": is_ip,
        f"{prefix}.is_individual": is_individual,
        f"{prefix}.signs_self": signs_self,
        f"{prefix}.signs_as_statutory_body": signs_as_body,
        f"{prefix}.signs_by_power_of_attorney": signs_by_poa,
        f"{prefix}.organization_statutory_body": is_organization and signs_as_body,
        f"{prefix}.organization_power_of_attorney": is_organization and signs_by_poa,
        f"{prefix}.individual_entrepreneur_self": is_ip and signs_self,
        f"{prefix}.individual_entrepreneur_power_of_attorney": is_ip and signs_by_poa,
        f"{prefix}.individual_self": is_individual and signs_self,
        f"{prefix}.individual_power_of_attorney": is_individual and signs_by_poa,
    }
