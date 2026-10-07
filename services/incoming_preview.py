"""Read-only, conservative suggestions for an already durable incoming request."""

import re

from schemas_incoming import IncomingPreview
from services.bot_quick_order_service import BotQuickOrderService
from services.order_scenarios import workflow_for_service_type

# Detect each explicit kind independently: the bot's priority ordering alone
# would turn a mixed or alternative request into a confident single scenario.
SERVICE_PATTERNS = {
    "maintenance": r"(?-i:\bТО\b)|\b(?:обслуживан\w*|чистк\w*|сервис)\b|\bто\s+(?:квартир\w*|кондиционер\w*)\b",
    "repair": r"\b(?:ремонт\w*|диагност\w*)\b|не\s+(?:работает|холодит)",
    "dismantling": r"\bдемонтаж\w*\b|снять\s+кондиционер",
    "pre_install": r"\b(?:заклад\w*|трасс\w*)\b",
    "install_only": r"\b(?:монтаж\w*|установ\w*)\b",
    "turnkey": r"\b(?:куп\w*|подбор\w*|продаж\w*|поставк\w*)\b",
}
UNCERTAIN = re.compile(r"\b(?:не|нет|без|или|либо|возможно|наверное|может|пока|уточнить|неизвест\w*)\b|\?", re.I)

# A description of cancelled, refused, conditional or past work is not a request.
# Abstain for the whole source even when the qualifier is in a separate clause.
NON_REQUEST = re.compile(
    r"\b(?:отмен\w*|отказ\w*|передум\w*|если|понадоб\w*|"
    r"ранее|раньше|прошл\w*|выполнен\w*|выполнил\w*|завершен\w*|завершил\w*|сделан\w*|проводил\w*)\b"
    r"|\bпри\s+необходимости\b|\bбыл[аио]?\s+(?:ремонт\w*|обслуживан\w*)\b"
    r"|\b(?:ремонт\w*|обслуживан\w*)(?:\s+\w+){0,2}\s+был[аио]?\b",
    re.I,
)


def incoming_preview(text: str) -> IncomingPreview:
    evidence = {}
    # Phone, addresses and dates are deliberately outside this parser. Existing
    # fields and the retained source clock have their own durable contracts.
    regions = []
    mentions = list(re.finditer(r"\b(?:район|р-н|микрорайон)\s+([^,;\n.!?]+)", text, re.I))
    # Count all mentions before filtering certainty: an uncertain alternative
    # must not make the remaining district look unambiguous.
    for match in mentions:
        if len(mentions) != 1:
            break
        value = match.group(1).strip()
        clause = text[max(text.rfind(';', 0, match.start()), text.rfind('\n', 0, match.start()), text.rfind(',', 0, match.start())) + 1:match.end()]
        if (not UNCERTAIN.search(clause) and text[match.end():match.end() + 1] != "?" and len(value) <= 100
                and not re.search(r"\d|\b(?:завтра|сегодня|послезавтра|адрес|улица|ул)\b", value, re.I)):
            regions.append(value)
    region = regions[0] if len(regions) == 1 else None
    if region:
        evidence["region_text"] = region

    kinds = set()
    uncertain = bool(NON_REQUEST.search(text))
    for clause in re.split(r"[,;\n.!]", text):
        found = {kind for kind, pattern in SERVICE_PATTERNS.items() if re.search(pattern, clause, re.I)}
        if found:
            # Symptom negation is the shared bot's explicit repair grammar.
            certainty_clause = re.sub(r"не\s+(?:работает|холодит)", "", clause, flags=re.I)
            uncertain |= bool(UNCERTAIN.search(certainty_clause))
            kinds |= found
            # Reuse bot parsing for clear clauses (padding recognizes initial ТО).
            inferred = BotQuickOrderService._infer_service_type(f" {clause} ")
            if inferred in found or len(found) == 1:
                evidence["service_type"] = clause.strip()
    if kinds == {"turnkey", "install_only"}:
        kinds = {"turnkey"}
    service = next(iter(kinds)) if len(kinds) == 1 and not uncertain else None
    if not service:
        evidence.pop("service_type", None)
    workflow = workflow_for_service_type(service) if service else None
    if workflow:
        evidence["workflow_type"] = evidence.get("service_type", text)
    return IncomingPreview(
        state="suggested" if region or service else "unknown",
        region_text=region, service_type=service, workflow_type=workflow,
        evidence=evidence, field_sources={key: "text" for key in evidence},
    )
