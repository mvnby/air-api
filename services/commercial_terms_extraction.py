"""Conservative local extraction; ambiguity is evidence, never a default."""
import re
from datetime import date
from decimal import Decimal

from schemas_business_document_terms import BusinessDocumentTermsPayload, PaymentScheduleItemPayload
from schemas_commercial_terms import CommercialSourceTerm

_DAY = re.compile(r"\b(\d{1,4})\s*(календарн\w*|банковск\w*|рабоч\w*)?\s*(?:дней|дня|день|дн\.)", re.I)
_PERCENT = re.compile(r"(\d{1,3}(?:[,.]\d{1,2})?)\s*%")
_PAYMENT = re.compile(r"оплат|аванс|предоплат|расч[её]т|постоплат", re.I)
_DELIVERY = re.compile(r"(?:срок\w*\s+(?:поставк|доставк)|поставк\w*\s+(?:в\s+течение|не\s+позднее|до\s)|доставк\w*\s+(?:в\s+течение|не\s+позднее|до\s))", re.I)
_EVENTS = (
    ("after_acceptance", r"после\s+(?:подписани\w*\s+акт|при[её]мк)|со\s+дня\s+подписани\w*\s+акт"),
    ("after_work", r"после\s+(?:выполнени\w*|выполненн\w*|завершени\w*|окончани\w*)\s+работ|с\s+момента\s+(?:выполнени\w*|завершени\w*)\s+работ"),
    ("after_supply", r"после\s+(?:поставк|доставк|получени\w*\s+(?:товар|оборудован))"),
    ("before_supply", r"до\s+(?:поставк|доставк)"),
    ("before_work", r"до\s+(?:начала|выполнени\w*)\s+работ"),
)


def extract_commercial_terms(raw: str, *, source: str) -> list[CommercialSourceTerm]:
    terms = []
    coverage_issues = []
    raw = str(raw or "")
    if len(raw) > 180000:
        coverage_issues.append("Текст источника обрезан; проверьте оригинал")
    # Keep decimal amounts and dates intact; semicolons separate payment stages.
    for paragraph in re.split(r"[\n;]+|(?<=[.!?])\s+(?=[А-ЯA-Z])", raw[:180000]):
        text = " ".join(paragraph.split())
        if not text:
            continue
        if len(text) > 2000:
            for kind, matcher in (("payment", _PAYMENT), ("delivery", _DELIVERY)):
                if matcher.search(text):
                    issue = "Длинное условие не разобрано полностью; проверьте оригинал"
                    coverage_issues.append(issue)
                    terms.append(CommercialSourceTerm(kind=kind, source=source[:255], evidence=text[:2000], issues=[issue]))
            continue
        for kind, matcher in (("payment", _PAYMENT), ("delivery", _DELIVERY)):
            if not matcher.search(text):
                continue
            issues = []
            days_matches = list(_DAY.finditer(text))
            due_days = int(days_matches[0][1]) if len(days_matches) == 1 and 0 < int(days_matches[0][1]) <= 3650 else None
            day_kind = None
            if due_days:
                day_word = (days_matches[0][2] or "").lower()
                day_kind = next((value for prefix, value in (("календар", "calendar"), ("банков", "banking"), ("рабоч", "working")) if day_word.startswith(prefix)), None)
                if not day_kind:
                    issues.append("Не указан вид дней: календарные, банковские или рабочие")
            elif days_matches:
                issues.append("Срок содержит несколько значений или выходит за допустимые пределы")
            events = [(event, match.group(0)) for event, pattern in _EVENTS if (match := re.search(pattern, text, re.I))]
            due_event, trigger = events[0] if len(events) == 1 else (None, None)
            if kind == "payment" and not due_event:
                issues.append("Не определено событие, от которого считается срок оплаты")
            # A percentage is meaningful only when unique in this explicit stage.
            percents = list(_PERCENT.finditer(text))
            share = Decimal(percents[0][1].replace(",", ".")) if len(percents) == 1 else None
            if share is not None and not 0 < share <= 100:
                share = None
            if kind == "payment" and not percents and re.search(r"(?:в полном объ[её]ме|полная оплата|полный расч[её]т)", text, re.I):
                share = Decimal("100")
            if kind == "payment" and share is None:
                issues.append("Доля платежа не указана однозначно")
            deadline = None
            found_date = re.search(r"\b(\d{2})[.](\d{2})[.](\d{4})\b", text) if kind == "delivery" else None
            if found_date:
                try:
                    deadline = date(int(found_date[3]), int(found_date[2]), int(found_date[1])).isoformat()
                except ValueError:
                    issues.append("Дата поставки некорректна")
            if kind == "delivery" and due_days and not re.search(r"(?:с\s+(?:момента|даты|дня)|после)\s+\S", text, re.I):
                issues.append("Не указано событие, от которого считается срок поставки")
            terms.append(CommercialSourceTerm(kind=kind, source=source[:255], evidence=text, share_percent=share if kind == "payment" else None,
                due_days=due_days, day_kind=day_kind, due_event=due_event if kind == "payment" else None,
                trigger_text=trigger or (text[:500] if kind == "delivery" else None), deadline=deadline, issues=issues))
    if len(terms) > 100:
        coverage_issues.append("Найдено больше 100 условий; часть источника не показана")
    result = terms[:100]
    if coverage_issues:
        for term in result:
            term.issues.extend(issue for issue in dict.fromkeys(coverage_issues) if issue not in term.issues)
    return result


def suggest_document_terms(terms: list[CommercialSourceTerm]) -> BusinessDocumentTermsPayload | None:
    payment = [term for term in terms if term.kind == "payment"]
    delivery = [term for term in terms if term.kind == "delivery"]
    if len(payment) > 20 or any(term.issues for term in terms):
        return None
    complete = payment and all(not term.issues and term.share_percent is not None and term.due_event for term in payment)
    if not complete or sum(term.share_percent for term in payment) != Decimal("100"):
        return None
    deadlines = {term.deadline for term in delivery if term.deadline}
    conditions = "\n".join(term.evidence for term in delivery)
    if len(deadlines) > 1 or len(conditions) > 8000:
        return None
    try:
        return BusinessDocumentTermsPayload(
            payment_schedule=[PaymentScheduleItemPayload(share_percent=term.share_percent, due_event=term.due_event,
                due_days=term.due_days, due_day_kind=term.day_kind or "calendar", note=term.evidence[:1000]) for term in payment],
            delivery_deadline=next(iter(deadlines)) if len(deadlines) == 1 else None,
            additional_conditions=conditions or None,
        )
    except ValueError:
        # Historical metadata may contain invalid dates or non-renderable amounts.
        return None
