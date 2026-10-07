"""Conservative explicit instructions and immutable qualification context."""

import re
from copy import deepcopy


CLARIFICATION_TITLE = "Уточнить адрес / созвониться перед выездом"


def explicit_instructions(text: str) -> tuple[bool, bool]:
    """Recognize only standalone positive instructions, never missing fields.

    Free prose, questions, negations and uncertain suggestions remain source text.
    Callers can provide structured flags for instructions outside this small grammar.
    """
    clauses = [part.strip().lower() for part in re.split(r"[;\n.!]", text)]
    address = any(re.fullmatch(r"(?:точный\s+)?адрес\s+уточнить|уточнить\s+(?:точный\s+)?адрес", part) for part in clauses)
    call = any(re.fullmatch(r"(?:предварительно\s+)?(?:созвониться|позвонить)\s+перед\s+выездом", part) for part in clauses)
    return address or call, call


def qualification_context(lead) -> dict:
    return {
        **deepcopy(lead.intake_meta),
        "lead_id": lead.id,
        "lead_version": lead.version,
        "request_text": lead.request_text,
        "name": lead.name,
        "phone": lead.phone,
        "email": lead.email,
        "agreement_status": "customer_wish",
    }
