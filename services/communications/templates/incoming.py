"""Bounded escaped Telegram rendering for tenant incoming snapshots."""

import re
from uuid import UUID
from zoneinfo import ZoneInfo

from core.config import settings
from services.communications.incoming_contracts import TenantIncomingCreatedPayloadV1
from services.communications.templates.website import _escape_bounded, _ensure_telegram_length

SOURCE_LABELS = {
    "phone": "Телефон", "bot": "Telegram", "email": "Почта",
    "manager": "Менеджер", "referral": "Рекомендация",
    "belzakupki": "Белзакупки", "other": "Другое", "site": "Сайт",
}
STATUS_LABELS = {"recommend": "🟢 Можно рассмотреть", "review": "🟡 На проверку", "skip": "⚪ Мимо"}
GENERAL_PROJECT = re.compile(
    r"^(?:(?:текущий |капитальный )?ремонт|реконструкция|модернизация)"
    r"\s+(?:помещен|здани|объект|сооружен)", re.IGNORECASE,
)
WORK_SUBTITLE = re.compile(
    r"\((?P<work>(?:перенос|демонтаж|монтаж|установка|ремонт|диагностика|обслуживание)"
    r"\s+[^()]{1,80})\)\s*$", re.IGNORECASE,
)
MINSK = ZoneInfo("Europe/Minsk")


def manager_incoming_url(entity_type: str, entity_id: int) -> str:
    route = f"leads?incomingId={entity_id}" if entity_type == "lead" else f"orders/kanban?orderId={entity_id}"
    return f"{settings.MANAGER_BASE_URL.rstrip('/')}/{route}"


def tender_heading(title: str) -> str:
    subtitle = WORK_SUBTITLE.search(title)
    if subtitle and GENERAL_PROJECT.match(title):
        work = subtitle["work"]
        return work[0].upper() + work[1:]
    if len(title) > 145:
        return (title[:145].rsplit(" ", 1)[0] or title[:145]) + "…"
    return title


def _visible_reference(reference: str | None) -> str:
    if not reference:
        return ""
    try:
        UUID(reference)
    except ValueError:
        return f" · {_escape_bounded(reference, max_length=80)}"
    return ""


def _tender_lines(payload: TenantIncomingCreatedPayloadV1) -> list[str]:
    card = payload.tender
    assert card is not None
    heading = _escape_bounded(tender_heading(card.title), max_length=146)
    source = _escape_bounded(card.source_label, max_length=80)
    if source.casefold() == "белорусская универсальная товарная биржа":
        source = "БУТБ"
    contact = [
        f"{label}: {_escape_bounded(value, max_length=limit)}"
        for label, value, limit in (
            ("👤 Заказчик", payload.name, 180),
            ("📍 Место работ", card.location, 200),
            ("📱 Телефон", payload.phone, 80),
            ("📧 Почта", payload.email, 160),
        )
        if value
    ]
    details = []
    if card.deadline_at:
        local = card.deadline_at.astimezone(MINSK)
        details.append(f"⏳ Подать до {local:%d.%m.%Y, %H:%M}")
    if card.quantity:
        details.append(f"📋 Объём: {_escape_bounded(card.quantity, max_length=80)}")
    if card.budget_amount is not None and card.budget_currency:
        currency = _escape_bounded(card.budget_currency, max_length=12)
        amount = f"{card.budget_amount:,.2f}".replace(",", "\u202f").replace(".", ",")
        details.append(f"💰 Оценочный бюджет: {amount} {currency}")
    reason = _escape_bounded(card.reason, max_length=180)
    lines = [f"📌 <b>{heading}</b>"]
    for section in (contact, details):
        if section:
            lines.extend(["", *section])
    lines.extend([
        "", f"{STATUS_LABELS[card.status]} · {reason}",
        f"Тендер №{payload.entity_id} · {source}{_visible_reference(card.reference)}",
    ])
    return lines


def render_tenant_incoming_v1(context, *, text_link: bool = True) -> str:
    payload = TenantIncomingCreatedPayloadV1.model_validate(context)
    if payload.tender:
        lines = _tender_lines(payload)
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
