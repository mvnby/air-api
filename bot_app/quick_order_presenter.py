"""Pure Telegram presentation helpers for API quick-order contracts."""

from html import escape

from api_contracts.bot import BotQuickOrderDraft


def quick_order_to_dict(draft: BotQuickOrderDraft | dict) -> dict:
    return BotQuickOrderDraft.model_validate(draft).model_dump(mode="json")


def _display_target_date(draft: BotQuickOrderDraft) -> str | None:
    return draft.target_date.strftime("%d.%m.%Y %H:%M") if draft.target_date else None


def _address_check_text(draft: BotQuickOrderDraft) -> str | None:
    check = draft.address_check
    if check is None:
        return None
    if check.status == "confirmed" and check.suggestion:
        return f"{check.message}: {check.suggestion}"
    if check.suggestion:
        return f"{check.message}. Вариант: {check.suggestion}"
    return check.message


def format_quick_order_preview(draft_value: BotQuickOrderDraft | dict) -> str:
    draft = BotQuickOrderDraft.model_validate(draft_value)
    address_check_text = _address_check_text(draft)
    lines = [
        "<b>Черновик заказа</b>",
        f"Клиент: {escape(draft.name or 'не указан')}",
        f"Телефон: {escape(draft.phone or 'не указан')}",
        f"Адрес: {escape(draft.address or 'не указан')}",
        f"Услуга: {escape(draft.service_label)}",
        f"Дата: {escape(_display_target_date(draft) or 'не указана')}",
        "",
        f"<i>{escape(draft.request_text)}</i>",
    ]
    if address_check_text:
        lines.insert(4, f"Проверка адреса: {escape(address_check_text)}")
    return "\n".join(lines)


def format_quick_order_preview_rich_html(
    draft_value: BotQuickOrderDraft | dict,
) -> str:
    draft = BotQuickOrderDraft.model_validate(draft_value)
    address_check_text = _address_check_text(draft)
    rich_html = (
        "<h3>Черновик заказа</h3>"
        "<p>"
        f"<b>Клиент:</b> {escape(draft.name or 'не указан')}<br/>"
        f"<b>Телефон:</b> {escape(draft.phone or 'не указан')}<br/>"
        f"<b>Адрес:</b> {escape(draft.address or 'не указан')}<br/>"
        f"{('<b>Проверка адреса:</b> ' + escape(address_check_text) + '<br/>') if address_check_text else ''}"
        f"<b>Услуга:</b> {escape(draft.service_label)}<br/>"
        f"<b>Дата:</b> {escape(_display_target_date(draft) or 'не указана')}"
        "</p>"
    )
    if draft.request_text:
        rich_html += f"<blockquote>{escape(draft.request_text)}</blockquote>"
    return rich_html
