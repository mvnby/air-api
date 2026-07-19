"""Validation and fallback rendering for staff task notification events."""

from html import escape

from services.communications.staff_task_contracts import (
    STAFF_TASK_EVENT_TYPES,
    STAFF_TASK_TEMPLATE_KEYS,
    StaffTaskNotificationPayloadV1,
)


_TITLES = {
    "assigned": "Новая задача",
    "rescheduled": "Задача изменена",
    "canceled": "Задача отменена",
    "departure_reminder": "Скоро выезд",
}


def plan_staff_task_event(
    *, event_type: str, payload: dict
) -> tuple[str, StaffTaskNotificationPayloadV1]:
    parsed = StaffTaskNotificationPayloadV1.model_validate(payload)
    if STAFF_TASK_EVENT_TYPES[parsed.event_kind] != event_type:
        raise ValueError("Staff task event type does not match payload kind")
    return STAFF_TASK_TEMPLATE_KEYS[parsed.event_kind], parsed


def validate_staff_task_template(
    *, template_key: str, render_context: dict
) -> StaffTaskNotificationPayloadV1:
    payload = StaffTaskNotificationPayloadV1.model_validate(render_context)
    if STAFF_TASK_TEMPLATE_KEYS[payload.event_kind] != template_key:
        raise ValueError("Staff task template does not match payload kind")
    return payload


def render_staff_task_v1(payload: StaffTaskNotificationPayloadV1) -> str:
    lines = [
        f"<b>{_TITLES[payload.event_kind]}</b>",
        f"Заказ #{payload.order_id}: {escape(payload.stage_name)}",
    ]
    if payload.start_time:
        lines.append(f"Время: {payload.start_time.strftime('%d.%m.%Y %H:%M')}")
    if payload.address:
        lines.append(f"Адрес: {escape(payload.address)}")
    return "\n".join(lines)
