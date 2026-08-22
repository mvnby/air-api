from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator


AnalyticsProvider = Literal[
    "yandex_metrika",
    "yandex_direct",
    "google_analytics",
    "google_ads",
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
