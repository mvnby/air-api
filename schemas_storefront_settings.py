"""Closed, public-safe settings for one storefront."""

from datetime import datetime
import re
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.input_validation import validate_optional_email, validate_optional_phone


ServiceDirection = Literal["installation", "pre_install", "dismantling", "maintenance", "repair"]
SERVICE_DIRECTIONS: dict[str, tuple[str, str]] = {
    "installation": ("Монтаж кондиционеров", "Установка и запуск кондиционера по согласованной схеме."),
    "pre_install": ("Закладка коммуникаций", "Прокладка трассы для кондиционера до чистовой отделки."),
    "dismantling": ("Демонтаж кондиционеров", "Снятие кондиционера для замены или переноса."),
    "maintenance": ("Обслуживание кондиционеров", "Чистка, профилактика и проверка работы кондиционера."),
    "repair": ("Ремонт кондиционеров", "Диагностика неисправности и согласование необходимого ремонта."),
}


class StorefrontSiteSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str = Field(min_length=1, max_length=160)
    city: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=80)
    email: str = Field(default="", max_length=254)
    address: str = Field(default="", max_length=500)
    work_hours: str = Field(default="", max_length=300)
    support_telegram_url: str = Field(default="", max_length=300)
    logo_asset_id: int | None = Field(default=None, ge=1)
    compact_logo_asset_id: int | None = Field(default=None, ge=1)

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        return validate_optional_email(value) or ""

    @field_validator("phone")
    @classmethod
    def phone_is_valid(cls, value: str) -> str:
        return validate_optional_phone(value) or ""

    @field_validator("support_telegram_url")
    @classmethod
    def telegram_link_is_valid(cls, value: str) -> str:
        if not value:
            return ""
        if value.startswith("@"):
            value = "https://t.me/" + value[1:]
        parsed = urlsplit(value)
        username = parsed.path.strip("/")
        query = parse_qs(parsed.query, keep_blank_values=True)
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != "t.me"
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", username)
            or parsed.fragment
            or set(query) - {"start"}
            or (query and (len(query.get("start", [])) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", query["start"][0])))
        ):
            raise ValueError("Укажите ссылку https://t.me/имя или @имя контакта поддержки")
        return value


class ServiceDirectionSetting(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: ServiceDirection
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=5000)
    enabled: bool = False


class StorefrontSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site: StorefrontSiteSettings
    services: list[ServiceDirectionSetting] = Field(min_length=5, max_length=5)
    version: int = Field(ge=0)

    @model_validator(mode="after")
    def all_service_directions_are_explicit(self):
        if {item.key for item in self.services} != set(SERVICE_DIRECTIONS):
            raise ValueError("Укажите каждое из пяти направлений услуг ровно один раз")
        self.services.sort(key=lambda item: tuple(SERVICE_DIRECTIONS).index(item.key))
        return self


class StorefrontSettingsResponse(StorefrontSettingsPayload):
    site: "StorefrontSiteSettingsResponse"
    updated_at: datetime | None = None


class StorefrontSiteSettingsResponse(StorefrontSiteSettings):
    logo_url: str | None = None
    compact_logo_url: str | None = None


class StorefrontBrandResponse(BaseModel):
    display_name: str
    logo_url: str | None = None
    compact_logo_url: str | None = None


def default_service_directions(*, enabled: bool) -> list[ServiceDirectionSetting]:
    return [
        ServiceDirectionSetting(key=key, title=title, description=description, enabled=enabled)
        for key, (title, description) in SERVICE_DIRECTIONS.items()
    ]
