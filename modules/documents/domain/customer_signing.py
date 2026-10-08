"""Presentation-only customer signing fields shared by document adapters."""

from typing import Any

from .party import ORGANIZATION, SELF, normalize_signing_mode


CUSTOMER_POSITION_LINE = "____________________________ (должность, род. падеж)"
CUSTOMER_NAME_LINE = "________________________________________ (ФИО, род. падеж)"
CUSTOMER_BASIS_LINE = "________________________________________ (основание полномочий)"


def customer_signing_text(
    *, entity_type: str, signing_mode: Any,
    signer_position: Any = None, signer_name: Any = None, acting_basis: Any = None,
) -> dict[str, str]:
    """Keep known facts and give applicable unknown fields room for handwriting.

    These strings are output values, never customer records or snapshot facts.
    A personal signature has no position/authority fields; a representative of
    an individual or entrepreneur needs authority, but no organization position.
    """
    name = str(signer_name or "")
    if normalize_signing_mode(entity_type, signing_mode) == SELF:
        return {
            "signer_position": "", "acting_basis": "",
            "signer_name": name if name.strip() else "",
        }
    position = str(signer_position or "")
    basis = str(acting_basis or "")
    return {
        "signer_position": (
            position if position.strip() else CUSTOMER_POSITION_LINE
        ) if entity_type == ORGANIZATION else "",
        "acting_basis": basis if basis.strip() else CUSTOMER_BASIS_LINE,
        "signer_name": name if name.strip() else CUSTOMER_NAME_LINE,
    }
