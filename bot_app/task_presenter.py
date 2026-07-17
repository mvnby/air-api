"""Pure Telegram presentation helpers for task cards and reports."""

from datetime import datetime
from html import escape
from typing import Any


def _task_value(task: dict[str, Any] | Any, field: str, default: Any = None) -> Any:
    if isinstance(task, dict):
        return task.get(field, default)
    return getattr(task, field, default)


def task_to_dict(task: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(task, dict):
        return task
    model_dump = getattr(task, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    raise TypeError("Unsupported task contract")


def build_stage_report(
    *,
    text: str | None = None,
    caption: str | None = None,
    photo_file_id: str | None = None,
    document_file_id: str | None = None,
    document_name: str | None = None,
) -> str:
    body = (text or caption or "").strip()
    lines: list[str] = [body] if body else []
    attachments: list[str] = []

    if photo_file_id:
        attachments.append(f"Фото: {photo_file_id}")

    if document_file_id:
        safe_name = " ".join((document_name or "файл").split())[:120] or "файл"
        attachments.append(f"Документ: {safe_name} ({document_file_id})")

    if attachments:
        if lines:
            lines.append("")
        lines.append("Вложения:")
        lines.extend(f"- {attachment}" for attachment in attachments)

    return "\n".join(lines).strip()


def format_tasks(tasks: list[dict[str, Any] | Any]) -> str:
    if not tasks:
        return "У вас нет ближайших задач."
    lines = ["<b>Мои ближайшие задачи</b>"]
    for task in tasks:
        dt = _task_value(task, "start_time")
        date_text = dt.strftime("%d.%m.%Y %H:%M") if isinstance(dt, datetime) else "время не назначено"
        lines.extend(
            [
                "",
                f"<b>#{_task_value(task, 'order_id')} - {escape(str(_task_value(task, 'title', 'Задача')))}</b>",
                f"Дата: {escape(date_text)}",
                f"Клиент: {escape(str(_task_value(task, 'customer_name') or 'Клиент'))}",
                f"Телефон: {escape(str(_task_value(task, 'customer_phone') or 'не указан'))}",
                f"Адрес: {escape(str(_task_value(task, 'address') or 'не указан'))}",
            ]
        )
        comment = _task_value(task, "comment")
        if comment:
            lines.append(f"Комментарий: {escape(str(comment))}")
    return "\n".join(lines)


def format_tasks_rich_html(tasks: list[dict[str, Any] | Any]) -> str:
    if not tasks:
        return "<h3>Мои ближайшие задачи</h3><p>У вас нет ближайших задач.</p>"

    blocks = ["<h3>Мои ближайшие задачи</h3>"]
    for task in tasks:
        dt = _task_value(task, "start_time")
        date_text = dt.strftime("%d.%m.%Y %H:%M") if isinstance(dt, datetime) else "время не назначено"
        blocks.append(
            "<p>"
            f"<b>#{_task_value(task, 'order_id')} - {escape(str(_task_value(task, 'title', 'Задача')))}</b><br/>"
            f"<b>Дата:</b> {escape(date_text)}<br/>"
            f"<b>Клиент:</b> {escape(str(_task_value(task, 'customer_name') or 'Клиент'))}<br/>"
            f"<b>Телефон:</b> {escape(str(_task_value(task, 'customer_phone') or 'не указан'))}<br/>"
            f"<b>Адрес:</b> {escape(str(_task_value(task, 'address') or 'не указан'))}"
            "</p>"
        )
        comment = _task_value(task, "comment")
        if comment:
            blocks.append(f"<blockquote>{escape(str(comment))}</blockquote>")
    return "".join(blocks)
