"""Small Telegram projections of existing tender evidence."""

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from schemas_tender_qualification import TenderDocumentFragment, TenderQualificationFact
from services.belzakupki_canonical_identity import canonical_procurement_url, canonical_tender_url
from services.communications.incoming_contracts import TenderCard
from services.tender_qualification import (
    _document_facts, _matches_location, _work_types, execution_address_text, load_mvn_tender_profile,
)

PROCUREMENT_NUMBER = re.compile(r"\bauc\d{5,}\b", re.I)
PROCUREMENT_SUBJECT = re.compile(
    r"\b(?:тендер\w*|госзакупк\w*|запрос ценовых предложений|заявка о ценах|"
    r"маркетингов\w+ исследован\w*|приглашени\w* к участию в закупке|процедур\w* закупки)\b", re.I,
)
PROCUREMENT_BODY = re.compile(r"\b(?:приглашаем (?:вас )?к участию в закупке|запрос ценовых предложений|заявка о ценах)\b", re.I)
URL = re.compile(r"https?://[^\s<>\x22]+", re.I)
WORK_LABELS = {
    "diagnostics": "Диагностика кондиционеров",
    "repair": "Ремонт кондиционеров",
    "maintenance": "ТО кондиционеров",
    "supply_with_installation": "Поставка с монтажом",
    "installation": "Монтаж кондиционеров",
    "supply_only": "Только поставка",
    "ventilation": "Вентиляция",
}
SOURCE_LABELS = {
    "goszakupki.by": "Госзакупки",
    "icetrade.by": "ICETRADE",
    "zakupki.butb.by": "БЕЛОРУССКАЯ УНИВЕРСАЛЬНАЯ ТОВАРНАЯ БИРЖА",
}
EXPLICIT_SUPPLY = re.compile(r"\b(?:только поставк\w*|без (?:выполнения )?монтаж\w*)\b", re.I)
MAX_TENDER_CARD_TEXT = 120_000


def _text(value, limit):
    if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
        return None
    return " ".join(str(value).split())[:limit] or None


def _date(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def _number(value):
    text = _text(value, 70)
    if not text:
        return None
    match = re.fullmatch(r"([0-9]{1,3}(?: [0-9]{3})+|[0-9]{1,12})([,.][0-9]{1,2})?(?: ([A-Za-z]{3}))?", text)
    if not match:
        return None
    try:
        value = Decimal(match[1].replace(" ", "") + (match[2] or "").replace(",", "."))
    except InvalidOperation:
        return None
    return (value, match[3]) if value < 10**13 else None


def _assess(title, facts, location, deadline, *, confirmed):
    work = {kind for kind, required in _work_types(title) if required}
    work.update(fact.work_type for fact in facts if fact.kind == "work_scope" and fact.work_required)
    profile = load_mvn_tender_profile()
    areas = [
        fact for fact in facts if fact.kind == "execution_address"
    ] or ([TenderQualificationFact(kind="execution_address", value=location, confidence="high")] if location else [])
    local = bool(areas) and all(_matches_location(fact, profile.preferred_locations) for fact in areas)
    within_area = bool(areas) and all(
        _matches_location(fact, profile.preferred_locations + profile.travel_locations) for fact in areas
    )
    if deadline and deadline <= datetime.now(timezone.utc):
        return "skip", "Срок подачи истёк"
    if {fact.value for fact in facts if fact.kind == "sole_proprietor_eligibility"} == {"excluded"}:
        return "skip", "Участие ИП исключено"
    if work == {"supply_only"} and (
        EXPLICIT_SUPPLY.search(title) or any(
            fact.work_type == "supply_only" and EXPLICIT_SUPPLY.search(fact.value) for fact in facts
        )
    ):
        return "skip", WORK_LABELS["supply_only"]
    if work == {"ventilation"} and areas and not local and not any(
        _matches_location(fact, profile.preferred_locations) for fact in areas
    ):
        return "skip", "Вентиляция за пределами Витебска"
    relevant = [kind for kind in WORK_LABELS if kind in work and profile.service_priorities.get(kind, 0) > 0]
    contradictions = any(
        fact.kind == "work_scope" and fact.work_required is False and (
            fact.work_type in work or fact.work_type == "installation" and "supply_with_installation" in work
        ) for fact in facts
    )
    if confirmed and relevant and within_area and deadline and not contradictions and work <= set(relevant):
        return "recommend", " / ".join(WORK_LABELS[kind] for kind in relevant[:2])
    return "review", "Нужно проверить ТЗ"


def _document_facts_from(texts, *, max_chars=16_000):
    if len(texts) > 8 or any(len(value) > max_chars for value in texts) or sum(map(len, texts)) > MAX_TENDER_CARD_TEXT:
        return []
    fragments = [
        TenderDocumentFragment(document_id=str(index), filename="Текст вложения", text=value)
        for index, value in enumerate(texts) if value.strip()
    ]
    facts, suspicious = _document_facts(fragments, additional_kinds=("equipment_count",))
    return [] if suspicious else facts


def _one_fact(facts, kind, *, field="value"):
    values = {getattr(fact, field) for fact in facts if fact.kind == kind and getattr(fact, field) is not None}
    return next(iter(values)) if len(values) == 1 else None


def _location(facts, fallback=None):
    addresses = list(dict.fromkeys(execution_address_text(fact.value) for fact in facts if fact.kind == "execution_address"))
    if len(addresses) > 1:
        return f"{addresses[0][:160]} и ещё {len(addresses) - 1}"
    return _text(addresses[0] if addresses else fallback, 200)


def _submission_deadline(facts, fallback=None):
    deadlines = {fact.deadline_at for fact in facts if fact.kind == "submission_deadline" and fact.deadline_at}
    if fallback:
        deadlines.add(fallback)
    return next(iter(deadlines)) if len(deadlines) == 1 else None


def _document_budget(facts):
    values = {(fact.amount, fact.currency) for fact in facts if fact.kind == "estimated_budget"}
    if len(values) == 1:
        amount, currency = next(iter(values))
        if amount is not None and amount < 10**13:
            return amount, currency
    return None, None


def native_tender_card(provider, order_title, *, document_texts=()):
    tender = provider.get("tender") or {}
    title = _text(tender.get("title") or order_title, 300) or "Закупка"
    source_url = canonical_tender_url(tender)
    if not source_url:
        # Preserve known procurement URLs only; never put an arbitrary email/CRM link in a button.
        source_url = canonical_procurement_url(tender.get("url"))
    facts = _document_facts_from(document_texts, max_chars=MAX_TENDER_CARD_TEXT)
    location = _location(facts, tender.get("location"))
    portal_deadline = _date(tender.get("deadline_at")) if tender.get("deadline_kind", "submission") == "submission" else None
    deadline = _submission_deadline(facts, portal_deadline)
    matches = (provider.get("matches") or {}).values()
    confirmed = any(
        match.get("relevance_status") == "confirmed" and match.get("eligible") is True
        and match.get("updated_at") == provider.get("tender_updated_at")
        for match in matches if isinstance(match, dict)
    )
    status, reason = _assess(title, facts, location, deadline, confirmed=confirmed or bool(facts))
    budget = _number(tender.get("estimated_value"))
    document_budget, document_currency = _document_budget(facts)
    return TenderCard(
        title=title, source_label=SOURCE_LABELS.get(urlsplit(source_url).hostname, "Белзакупки") if source_url else "Белзакупки",
        source_url=source_url, reference=_text(tender.get("external_id"), 80),
        location=location, deadline_at=deadline,
        quantity=_text(_one_fact(facts, "equipment_count") or tender.get("quantity"), 80),
        budget_amount=budget[0] if budget else document_budget,
        budget_currency=_text(tender.get("currency") or (budget[1] if budget else document_currency), 12),
        status=status, reason=reason,
    )


def email_tender_card(subject, body, attachment_texts=(), *, summary=None):
    subject = subject or ""
    body = body or ""
    source_url = next(
        (safe for match in URL.finditer(subject + "\n" + body[:20000])
         if (safe := canonical_procurement_url(match[0].rstrip(").,;")))),
        None,
    )
    reference = PROCUREMENT_NUMBER.search(subject)
    if not (source_url or reference or PROCUREMENT_SUBJECT.search(subject) or PROCUREMENT_BODY.search(body[:3000])):
        return None
    subject_title = _text(subject, 300) or "Закупка из письма"
    summary_title = _text(summary.splitlines()[0], 180) if summary and summary.splitlines() else None
    title = summary_title if summary_title and not _work_types(subject_title) else subject_title
    facts = _document_facts_from(attachment_texts) + _document_facts_from((body,))
    location = _location(facts)
    deadline = _submission_deadline(facts)
    status, reason = _assess(subject_title, facts, location, deadline, confirmed=bool(facts))
    budget, currency = _document_budget(facts)
    return TenderCard(
        title=title, source_label=SOURCE_LABELS.get(urlsplit(source_url).hostname, "Почта") if source_url else "Почта",
        source_url=source_url, reference=reference[0] if reference else None, location=location,
        deadline_at=deadline, quantity=_text(_one_fact(facts, "equipment_count"), 80),
        budget_amount=budget, budget_currency=currency,
        status=status, reason=reason,
    )
