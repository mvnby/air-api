"""Bounded escaped Telegram rendering for tenant incoming snapshots."""

from zoneinfo import ZoneInfo

from core.config import settings
from services.communications.incoming_contracts import TenderCard, TenantIncomingCreatedPayloadV1
from services.communications.templates.website import _escape_bounded, _ensure_telegram_length, _format_amount

SOURCE_LABELS = {
    "phone": "Телефон", "bot": "Telegram", "email": "Почта",
    "manager": "Менеджер", "referral": "Рекомендация",
    "belzakupki": "Белзакупки", "other": "Другое", "site": "Сайт",
}
STATUS_LABELS = {"recommend": "Можно рассмотреть", "review": "На проверку", "skip": "Мимо"}
MINSK = ZoneInfo("Europe/Minsk")


def manager_incoming_url(entity_type: str, entity_id: int) -> str:
    route = f"leads?incomingId={entity_id}" if entity_type == "lead" else f"orders/kanban?orderId={entity_id}"
    return f"{settings.MANAGER_BASE_URL.rstrip('/')}/{route}"


def _tender_lines(card: TenderCard, entity_id: int) -> list[str]:
    source = _escape_bounded(card.source_label, max_length=80)
    reference = f" · {_escape_bounded(card.reference, max_length=80)}" if card.reference else ""
    heading = _escape_bounded(card.title, max_length=300)
    reason = _escape_bounded(card.reason, max_length=180)
    lines = [
        f"<b>Тендер №{entity_id} · {source}</b>{reference}",
        f"<b>{heading}</b>",
        f"{STATUS_LABELS[card.status]} · {reason}",
    ]
    if card.location:
        lines.append(f"Место работ: {_escape_bounded(card.location, max_length=200)}")
    if card.deadline_at:
        local = card.deadline_at.astimezone(MINSK)
        lines.append(f"<b>Подать до {local:%d.%m.%Y, %H:%M}</b>")
    if card.quantity:
        lines.append(f"Объём: {_escape_bounded(card.quantity, max_length=80)}")
    if card.budget_amount is not None and card.budget_currency:
        currency = _escape_bounded(card.budget_currency, max_length=12)
        lines.append(f"Бюджет: {_format_amount(card.budget_amount)} {currency}")
    return lines


def render_tenant_incoming_v1(context, *, text_link: bool = True) -> str:
    payload = TenantIncomingCreatedPayloadV1.model_validate(context)
    if payload.tender:
        lines = _tender_lines(payload.tender, payload.entity_id)
    else:
        source = _escape_bounded(SOURCE_LABELS.get(payload.source, payload.source), max_length=100)
        lines = [f"<b>Обращение №{payload.entity_id} · {source}</b>"]
        if payload.subject:
            lines.append(f"<b>{_escape_bounded(payload.subject, max_length=300)}</b>")
        for value, budget in ((payload.name, 160), (payload.phone, 80), (payload.email, 160)):
            if value:
                lines.append(_escape_bounded(value, max_length=budget))
        if payload.request_text:
            lines.extend(["", _escape_bounded(payload.request_text, max_length=360)])
    if text_link:
        url = _escape_bounded(manager_incoming_url(payload.entity_type, payload.entity_id), max_length=500)
        lines.extend(["", f'<a href="{url}">Открыть в Manager</a>'])
    return _ensure_telegram_length("\n".join(lines))
