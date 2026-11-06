"""Bounded, visitor-supplied context for a single website submission."""

import unicodedata
from typing import Literal
from urllib.parse import unquote

from pydantic import BaseModel, ConfigDict, Field, field_validator


WebsiteFormId = Literal[
    "contact", "checkout", "installation_calculator", "installation_estimate",
    "repair_diagnostic", "product_availability", "multi_split",
]

FORM_LABELS: dict[str, str] = {
    "contact": "Обратная связь",
    "checkout": "Оформление заказа",
    "installation_calculator": "Калькулятор монтажа",
    "installation_estimate": "Монтаж по фото",
    "repair_diagnostic": "Диагностика ремонта",
    "product_availability": "Сообщить о поступлении",
    "multi_split": "Подбор мультисплита",
}


class WebsiteSubmissionContext(BaseModel):
    """Untrusted page/form references; these do not select or confirm ordered work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page_path: str = Field(min_length=1, max_length=500)
    form_id: WebsiteFormId
    service_id: str | None = Field(default=None, min_length=1, max_length=80)
    product_id: int | None = Field(default=None, gt=0)

    @field_validator("page_path")
    @classmethod
    def validate_page_path(cls, value: str) -> str:
        decoded = unquote(value)
        if (
            not value.startswith("/") or value.startswith("//")
            or decoded.startswith("//")
            or any(char in value for char in "?#\\")
            or any(char in decoded for char in "?#\\")
            or any(unicodedata.category(char).startswith("C") for char in decoded)
        ):
            raise ValueError("page_path must be a pathname without origin, query, fragment or controls")
        return value

    @field_validator("service_id")
    @classmethod
    def validate_service_id(cls, value: str | None) -> str | None:
        if value is not None and (
            value != value.strip()
            or any(unicodedata.category(char).startswith("C") for char in value)
        ):
            raise ValueError("service_id must be plain text without controls")
        return value


def submission_context_meta(context: WebsiteSubmissionContext | None) -> dict:
    if context is None:
        return {}
    return {"submission_context": context.model_dump(mode="json", exclude_none=True)}


def append_submission_context(text: str | None, context: WebsiteSubmissionContext | None) -> str | None:
    if context is None:
        return text
    lines = [text] if text else []
    lines.extend([f"Форма: {FORM_LABELS[context.form_id]}", f"Страница: {context.page_path}"])
    if context.service_id:
        lines.append(f"Услуга на странице (контекст обращения): {context.service_id}")
    if context.product_id:
        lines.append(f"Товар на странице: #{context.product_id}")
    return "\n".join(lines)
