"""Bounded escaped Telegram rendering for tenant incoming snapshots."""

from core.config import settings
from services.communications.incoming_contracts import TenantIncomingCreatedPayloadV1
from services.communications.templates.website import _escape_bounded, _ensure_telegram_length


def render_tenant_incoming_v1(context) -> str:
    payload = TenantIncomingCreatedPayloadV1.model_validate(context)
    labels = {"phone": "Телефон", "bot": "Telegram", "email": "Почта",
              "manager": "Менеджер", "referral": "Рекомендация",
              "belzakupki": "Белзакупки", "other": "Другое", "site": "Сайт"}
    lines = [f"🔔 <b>НОВОЕ ОБРАЩЕНИЕ #{payload.entity_id}</b>",
             f"Источник: {_escape_bounded(labels.get(payload.source, payload.source), max_length=100)}"]
    for prefix, value, budget in (("👤", payload.name, 240), ("📱", payload.phone, 100),
                                  ("📧", payload.email, 254)):
        if value:
            lines.append(f"{prefix} {_escape_bounded(value, max_length=budget)}")
    if payload.request_text:
        lines.extend(["", _escape_bounded(payload.request_text, max_length=2600)])
    # The domain and route come from application configuration, never user input.
    route = (f"leads?incomingId={payload.entity_id}" if payload.entity_type == "lead"
             else f"orders/kanban?orderId={payload.entity_id}")
    url = f"{settings.MANAGER_BASE_URL.rstrip('/')}/{route}"
    lines.extend(["", f'<a href="{_escape_bounded(url, max_length=500)}">Открыть в Manager</a>'])
    return _ensure_telegram_length("\n".join(lines))
