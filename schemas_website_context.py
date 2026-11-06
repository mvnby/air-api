"""Bounded, visitor-supplied context for a single website submission."""

import unicodedata
from collections.abc import Mapping
from typing import Annotated, Any, Literal
from urllib.parse import unquote

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator


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


def validate_website_pathname(value: str) -> str:
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


class WebsiteInterestItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["product", "article", "service", "topic"]
    page_path: str = Field(min_length=1, max_length=500, strict=True)
    title: str = Field(min_length=1, max_length=160, strict=True)
    active_seconds: StrictInt = Field(ge=0, le=1800)
    product_id: StrictInt | None = Field(default=None, gt=0, exclude_if=lambda value: value is None)
    topics: list[Annotated[str, Field(min_length=1, max_length=80, strict=True)]] | None = Field(
        default=None, max_length=5, exclude_if=lambda value: value is None,
    )

    @field_validator("page_path")
    @classmethod
    def valid_path(cls, value: str) -> str:
        return validate_website_pathname(value)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return validate_interest_text(value)

    @field_validator("topics")
    @classmethod
    def valid_topics(cls, value: list[str] | None) -> list[str] | None:
        return [validate_interest_text(topic) for topic in value] if value is not None else None


class WebsiteInterests(BaseModel):
    """Optional consented attention, separate from the customer's requested work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    consent: Literal[True]
    items: list[WebsiteInterestItem] = Field(min_length=1, max_length=8)

    @field_validator("version", "consent", mode="before")
    @classmethod
    def exact_literals(cls, value: Any, info):
        if info.field_name == "consent" and value is not True:
            raise ValueError("Consent must be explicitly true")
        if info.field_name == "version" and (type(value) is not int or value != 1):
            raise ValueError("Unsupported interests version")
        return value

    @field_validator("items")
    @classmethod
    def by_attention(cls, value: list[WebsiteInterestItem]) -> list[WebsiteInterestItem]:
        return sorted(value, key=lambda item: item.active_seconds, reverse=True)


def validate_interest_text(value: str) -> str:
    if not value.strip() or any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError("Interest labels must be public plain text without controls")
    return value


class WebsiteSubmissionContext(BaseModel):
    """Untrusted page/form references; these do not select or confirm ordered work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page_path: str = Field(min_length=1, max_length=500)
    form_id: WebsiteFormId
    service_id: str | None = Field(default=None, min_length=1, max_length=80)
    product_id: int | None = Field(default=None, gt=0)
    interests: WebsiteInterests | None = Field(default=None, exclude_if=lambda value: value is None)

    @field_validator("interests", mode="wrap")
    @classmethod
    def optional_interests(cls, value: Any, handler) -> WebsiteInterests | None:
        try:
            return handler(value)
        except (ValueError, TypeError):
            # Optional attention must never reject an otherwise valid request.
            return None

    @field_validator("page_path")
    @classmethod
    def validate_page_path(cls, value: str) -> str:
        return validate_website_pathname(value)

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


def submission_context_identity(context: Mapping[str, Any]) -> dict[str, Any]:
    """Only passive attention is excluded from the business request identity."""
    return {key: value for key, value in context.items() if key != "interests"}


def website_interests_from_meta(meta: Any) -> WebsiteInterests | None:
    """Project only validated attention from the already scoped entity metadata."""
    if not isinstance(meta, dict):
        return None
    context = meta.get("submission_context")
    if not isinstance(context, dict):
        incoming = meta.get("incoming_intake")
        context = incoming.get("submission_context") if isinstance(incoming, dict) else None
    raw = context.get("interests") if isinstance(context, dict) else None
    if raw is None:
        return None
    try:
        return WebsiteInterests.model_validate(raw)
    except ValidationError:
        return None
