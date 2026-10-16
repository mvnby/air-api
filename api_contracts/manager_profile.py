"""Self-service profile fields; credentials and membership rights are separate."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ManagerOwnProfileResponse(BaseModel):
    staff_user_id: int
    display_name: str
    username: str | None = None
    phone: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    updated_at: datetime
    telegram_linked: bool
    telegram_username: str | None = None
    telegram_notifications_enabled: bool


class ManagerOwnProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_updated_at: datetime
    display_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=254)
    telegram_notifications_enabled: bool | None = None

    @field_validator("display_name")
    @classmethod
    def valid_name(cls, value: str | None) -> str:
        if not value or not value.strip():
            raise ValueError("Укажите имя")
        return value.strip()

    @field_validator("phone", "email")
    @classmethod
    def trim_contact(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("telegram_notifications_enabled")
    @classmethod
    def valid_consent(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("Укажите состояние уведомлений")
        return value


class ManagerOwnAvatarDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_updated_at: datetime
