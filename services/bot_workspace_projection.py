"""Minimal fields for the mobile CRM cards."""

from datetime import datetime
from zoneinfo import ZoneInfo

from api_contracts.bot_workspace import BotWorkspaceFact, BotWorkspaceRow


MINSK = ZoneInfo("Europe/Minsk")
PARTIES = {"individual": "Физлицо", "individual_entrepreneur": "ИП", "company": "Организация"}
ORDER_STATUSES = {"new_lead": "Новое обращение", "negotiation": "Переговоры", "execution": "В работе", "closed": "Закрыт"}
TASK_STATUSES = {"active": "В работе", "completed": "Выполнено", "cancelled": "Отменено"}
SOURCES = {"site": "Сайт", "email": "Почта", "bot": "Telegram", "phone": "Телефон", "manager": "Менеджер",
           "referral": "Рекомендация", "belzakupki": "Белзакупки", "other": "Другой источник"}


def short(value, limit=180):
    return " ".join(str(value or "").split())[:limit]


def when(value):
    if not value:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo:
        value = value.astimezone(MINSK)
    return value.strftime("%d.%m.%Y, %H:%M")


def facts(*entries):
    return [BotWorkspaceFact(label=label, value=str(value)[:1500], kind=kind[0] if kind else "text")
            for label, value, *kind in entries if value is not None and str(value).strip()]


def incoming_row(data):
    status = "В архиве" if data.archive else "Обращение"
    return BotWorkspaceRow(
        id=data.id, kind=data.entity_kind, title=short(data.title or data.customer_name or f"Обращение № {data.id}"),
        subtitle=short(data.customer_name or data.summary or data.phone),
        status="Закупка" if data.source_kind == "tender" and not data.archive else status, is_read=data.is_read,
    )


def incoming_facts(item):
    return facts(("Клиент", item.customer_name), ("Телефон", item.phone, "phone"), ("Email", item.email, "email"),
                 ("Адрес", item.customer_delivery_address or item.location), ("Источник", SOURCES.get(item.source, item.source)),
                 ("Получено", when(item.source_created_at or item.created_at)), ("Пожелание по сроку", item.requested_time_text))


def order_row(data):
    customer = data.get("customer") or {}
    return BotWorkspaceRow(
        id=data["id"], kind="order", title=f"№ {data['id']} · {short(data.get('title') or customer.get('name') or 'Заказ')}",
        subtitle=short(customer.get("name") if data.get("title") else data.get("delivery_address")),
        status="На паузе" if data.get("is_on_hold") else ORDER_STATUSES.get(data["status"], data["status"]),
    )


def byn(amount):
    return f"{amount:,.2f} BYN".replace(",", " ").replace(".", ",") if amount is not None else None


def order_equipment(order):
    groups = {
        proposal.id: {"name": proposal.name, "selected": proposal.is_selected, "equipment": []}
        for proposal in sorted(order.proposals, key=lambda row: (row.sort_order, row.id)) if not proposal.is_archived
    }
    groups[None] = {"name": "Оборудование заказа", "selected": not groups, "equipment": []}
    for link in sorted(order.product_links, key=lambda row: row.id):
        group = groups.get(link.proposal_id)
        if group is not None:
            group["equipment"].append({
                "title": link.title_snapshot or (link.product.title if link.product else "Оборудование"),
                "quantity": link.quantity, "unit_price": link.price, "currency": link.currency_snapshot or "BYN",
            })
    return [group for group in groups.values() if group["equipment"]]


def order_facts(data):
    customer = data.get("customer") or {}
    return facts(("Клиент", customer.get("name")), ("Контакт", data.get("contact_name")),
                 ("Телефон", data.get("contact_phone") or customer.get("phone"), "phone"),
                 ("Адрес", data.get("delivery_address")), ("Сумма", byn(data.get("total_amount"))),
                 ("К оплате", byn(data.get("balance_due"))), ("Следующий контакт", when(data.get("next_followup_date"))),
                 ("Замер", when(data.get("measurement_date"))), ("Выезд", when(data.get("installation_date"))))


def customer_row(data):
    return BotWorkspaceRow(
        id=data["id"], kind="customer", title=short(data["name"]), subtitle=short(data.get("phone") or data.get("email")),
        status=PARTIES.get(data.get("type"), data.get("type")),
    )


def customer_facts(data):
    contact = data.get("primary_contact") or {}
    return facts(("Телефон", data.get("phone") or contact.get("phone"), "phone"),
                 ("Email", data.get("email") or contact.get("email"), "email"), ("Контакт", contact.get("name")),
                 ("УНП", data.get("inn")), ("Адрес", data.get("actual_address") or data.get("last_delivery_address")),
                 ("Заказов на витрине", data["order_count"]))


def task_row(data):
    return BotWorkspaceRow(
        id=data.id, kind="task", title=short(data.text), subtitle=short(" · ".join(
            part for part in (data.assignee_name, when(data.due_at)) if part)),
        status=TASK_STATUSES.get(data.status, data.status),
    )


def task_facts(data):
    return facts(("Автор", data.author_name), ("Исполнитель", data.assignee_name), ("Срок", when(data.due_at)),
                 ("Напоминание", when(data.reminder_at)), ("Выполнено", when(data.completed_at)))
