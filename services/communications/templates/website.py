from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any, Mapping

from services.communications.contracts import (
    InstallationEstimateLeadCreatedPayloadV1,
    PublicContactLeadCreatedPayloadV1,
    PublicOrderCreatedPayloadV1,
    TenantWebsiteAvailabilityRequestedPayloadV1,
    TenantWebsiteCheckoutCreatedPayloadV1,
    TenantWebsiteContactLeadCreatedPayloadV1,
    TenantWebsiteRepairDiagnosticCreatedPayloadV1,
)


MAX_TELEGRAM_MESSAGE_LENGTH = 4096


class TemplateRenderError(ValueError):
    pass


def _escape_bounded(value: Any, *, max_length: int) -> str:
    source_value = "" if value is None else str(value)
    raw_value = "".join(
        " " if char in "\r\n\t" else char
        for char in source_value
        if char in "\r\n\t" or (ord(char) >= 32 and not 127 <= ord(char) < 160)
    )
    rendered = escape(raw_value)
    if len(rendered) <= max_length:
        return rendered

    budget = max(0, max_length - 3)
    parts: list[str] = []
    used = 0
    for char in raw_value:
        escaped_char = escape(char)
        if used + len(escaped_char) > budget:
            break
        parts.append(escaped_char)
        used += len(escaped_char)
    return "".join(parts) + ("..." if max_length >= 3 else "")


def _format_amount(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _ensure_telegram_length(text: str) -> str:
    if len(text) > MAX_TELEGRAM_MESSAGE_LENGTH:
        raise TemplateRenderError(
            f"Rendered Telegram message exceeds {MAX_TELEGRAM_MESSAGE_LENGTH} characters"
        )
    return text


def render_website_order_v1(
    context: PublicOrderCreatedPayloadV1 | Mapping[str, Any],
) -> str:
    payload = (
        context
        if isinstance(context, PublicOrderCreatedPayloadV1)
        else PublicOrderCreatedPayloadV1.model_validate(context)
    )
    lines = [
        f"🌐 <b>ЗАКАЗ С САЙТА #{payload.order_id}</b>",
        f"👤 {_escape_bounded(payload.customer.name, max_length=160)}",
        f"📱 {_escape_bounded(payload.customer.phone, max_length=80)}",
    ]
    if payload.customer.email:
        lines.append(f"📧 {_escape_bounded(payload.customer.email, max_length=254)}")
    if payload.customer.address:
        lines.append(f"📍 {_escape_bounded(payload.customer.address, max_length=250)}")
    if payload.comment:
        lines.append(f"💬 {_escape_bounded(payload.comment, max_length=400)}")

    lines.extend(["", "🛒 <b>Товары:</b>"])
    for item in payload.product_lines[:6]:
        line_total = item.unit_price * item.quantity
        lines.append(
            f"▫️ {_escape_bounded(item.title, max_length=120)} "
            f"x{item.quantity} — {_format_amount(line_total)} {payload.currency}"
        )
        if item.installation_included:
            lines.append(
                "   └ 🔧 Монтаж: "
                f"{_format_amount(item.installation_price)} {payload.currency}"
            )
    if len(payload.product_lines) > 6:
        lines.append(f"… ещё товаров: {len(payload.product_lines) - 6}")

    for item in payload.service_lines[:4]:
        line_total = item.unit_price * item.quantity
        lines.append(
            f"🔧 {_escape_bounded(item.title, max_length=120)} "
            f"x{item.quantity} — {_format_amount(line_total)} {payload.currency}"
        )
    if len(payload.service_lines) > 4:
        lines.append(f"… ещё услуг: {len(payload.service_lines) - 4}")

    lines.extend(
        [
            "",
            f"💰 <b>Итого: {_format_amount(payload.total_amount)} {payload.currency}</b>",
        ]
    )
    return _ensure_telegram_length("\n".join(lines))


def render_website_contact_lead_v1(
    context: PublicContactLeadCreatedPayloadV1 | Mapping[str, Any],
) -> str:
    payload = (
        context
        if isinstance(context, PublicContactLeadCreatedPayloadV1)
        else PublicContactLeadCreatedPayloadV1.model_validate(context)
    )
    lines = [
        f"🔔 <b>ЗАЯВКА С САЙТА #{payload.lead_id}</b>",
        f"👤 {_escape_bounded(payload.name, max_length=160)}",
        f"📱 {_escape_bounded(payload.phone, max_length=80)}",
    ]
    if payload.email:
        lines.append(f"📧 {_escape_bounded(payload.email, max_length=254)}")
    if payload.address:
        lines.append(f"📍 {_escape_bounded(payload.address, max_length=250)}")
    if payload.message:
        lines.extend(
            ["", f"💬 {_escape_bounded(payload.message, max_length=800)}"]
        )
    return _ensure_telegram_length("\n".join(lines))


def render_tenant_website_checkout_v1(
    context: TenantWebsiteCheckoutCreatedPayloadV1 | Mapping[str, Any],
) -> str:
    payload = (
        context
        if isinstance(context, TenantWebsiteCheckoutCreatedPayloadV1)
        else TenantWebsiteCheckoutCreatedPayloadV1.model_validate(context)
    )
    return render_website_order_v1(payload)


def render_tenant_website_contact_v1(
    context: TenantWebsiteContactLeadCreatedPayloadV1 | Mapping[str, Any],
) -> str:
    payload = (
        context
        if isinstance(context, TenantWebsiteContactLeadCreatedPayloadV1)
        else TenantWebsiteContactLeadCreatedPayloadV1.model_validate(context)
    )
    return render_website_contact_lead_v1(payload)


def render_installation_estimate_lead_v1(
    context: InstallationEstimateLeadCreatedPayloadV1 | Mapping[str, Any],
) -> str:
    payload = (
        context
        if isinstance(context, InstallationEstimateLeadCreatedPayloadV1)
        else InstallationEstimateLeadCreatedPayloadV1.model_validate(context)
    )
    lines = [
        f"📷 <b>МОНТАЖ ПО ФОТО #{payload.order_id}</b>",
        f"👤 {_escape_bounded(payload.name, max_length=160)}",
        f"📱 {_escape_bounded(payload.phone, max_length=80)}",
    ]
    if payload.email:
        lines.append(f"📧 {_escape_bounded(payload.email, max_length=254)}")
    if payload.address:
        lines.append(f"📍 {_escape_bounded(payload.address, max_length=250)}")
    if payload.description:
        lines.extend(
            ["", f"💬 {_escape_bounded(payload.description, max_length=800)}"]
        )
    categories = ", ".join(payload.photo_categories)
    lines.extend(
        [
            "",
            f"🖼 Фото: {payload.attachment_count}",
            f"Категории: {_escape_bounded(categories, max_length=300)}",
            "Статус: ожидает предварительной оценки",
        ]
    )
    return _ensure_telegram_length("\n".join(lines))


def render_tenant_website_availability_v1(
    context: TenantWebsiteAvailabilityRequestedPayloadV1 | Mapping[str, Any],
) -> str:
    payload = (
        context
        if isinstance(context, TenantWebsiteAvailabilityRequestedPayloadV1)
        else TenantWebsiteAvailabilityRequestedPayloadV1.model_validate(context)
    )
    heading = (
        "🔔 <b>ПОВТОРНЫЙ ЗАПРОС НА ПОСТУПЛЕНИЕ</b>"
        if payload.is_repeat
        else "🔔 <b>ЗАПРОС НА ПОСТУПЛЕНИЕ С САЙТА</b>"
    )
    lines = [
        heading,
        f"🆔 Заявка #{payload.order_id}",
        f"📦 {_escape_bounded(payload.product_title, max_length=180)}",
        f"🔗 /product/{_escape_bounded(payload.product_slug, max_length=200)}",
        f"📱 {_escape_bounded(payload.phone, max_length=80)}",
    ]
    if payload.name:
        lines.insert(
            4,
            f"👤 {_escape_bounded(payload.name, max_length=160)}",
        )
    return _ensure_telegram_length("\n".join(lines))


def render_tenant_website_repair_v1(
    context: TenantWebsiteRepairDiagnosticCreatedPayloadV1 | Mapping[str, Any],
) -> str:
    payload = (
        context
        if isinstance(context, TenantWebsiteRepairDiagnosticCreatedPayloadV1)
        else TenantWebsiteRepairDiagnosticCreatedPayloadV1.model_validate(context)
    )
    lines = [
        f"<b>ЗАЯВКА НА РЕМОНТ С САЙТА #{payload.order_id}</b>",
        f"Клиент: {_escape_bounded(payload.name, max_length=160)}",
        f"Телефон: {_escape_bounded(payload.phone, max_length=80)}",
        f"Симптом: {_escape_bounded(payload.symptom_label, max_length=180)}",
    ]
    if payload.address:
        lines.append(
            f"Адрес/район: {_escape_bounded(payload.address, max_length=300)}"
        )
    lines.append(f"Фото: {payload.photo_count}")
    return _ensure_telegram_length("\n".join(lines))
