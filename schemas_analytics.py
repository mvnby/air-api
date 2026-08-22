from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator


AnalyticsProvider = Literal[
    "yandex_metrika",
    "yandex_direct",
    "yandex_webmaster",
    "google_analytics",
    "google_ads",
    "google_search_console",
]


class AnalyticsConnectionItem(BaseModel):
    provider: AnalyticsProvider
    label: str
    description: str
    state: Literal["connected", "not_configured", "coming_soon", "error"]
    available: bool
    credentials_configured: bool = False
    counter_id: str | None = None
    counter_name: str | None = None
    site: str | None = None
    last_verified_at: datetime | None = None
    last_error_code: str | None = None
    connection_method: Literal["token", "oauth"] = "token"
    configuration: dict[str, str] = Field(default_factory=dict)


class AnalyticsConnectionListResponse(BaseModel):
    tenant_id: int
    storefront_id: int
    items: list[AnalyticsConnectionItem]


class YandexMetrikaConnectionUpsertPayload(BaseModel):
    counter_id: str = Field(min_length=1, max_length=32)
    oauth_token: SecretStr | None = None

    @field_validator("counter_id")
    @classmethod
    def validate_counter_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.isdigit():
            raise ValueError("ID счётчика должен состоять только из цифр")
        return normalized


class YandexDirectConnectionUpsertPayload(BaseModel):
    client_login: str | None = Field(default=None, max_length=255)
    oauth_token: SecretStr | None = None

    @field_validator("client_login")
    @classmethod
    def normalize_client_login(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None


class YandexWebmasterConnectionUpsertPayload(BaseModel):
    oauth_token: SecretStr | None = None


class GoogleAnalyticsAuthorizationPayload(BaseModel):
    property_id: str = Field(min_length=1, max_length=32)

    @field_validator("property_id")
    @classmethod
    def validate_property_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.isdigit():
            raise ValueError("ID ресурса GA4 должен состоять только из цифр")
        return normalized


class GoogleAdsAuthorizationPayload(BaseModel):
    customer_id: str = Field(min_length=1, max_length=32)
    login_customer_id: str | None = Field(default=None, max_length=32)

    @field_validator("customer_id")
    @classmethod
    def normalize_customer_id(cls, value: str) -> str:
        normalized = value.replace("-", "").strip()
        if not normalized.isdigit() or len(normalized) != 10:
            raise ValueError("ID Google Ads должен содержать 10 цифр")
        return normalized

    @field_validator("login_customer_id")
    @classmethod
    def normalize_login_customer_id(cls, value: str | None) -> str | None:
        normalized = str(value or "").replace("-", "").strip()
        if not normalized:
            return None
        if not normalized.isdigit() or len(normalized) != 10:
            raise ValueError("ID Google Ads должен содержать 10 цифр")
        return normalized


class AnalyticsAuthorizationUrlResponse(BaseModel):
    url: str
