"""Versioned response contracts for the internal Telegram bot API."""

from typing import Literal

from pydantic import BaseModel, Field


class BotApiHealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    api_version: Literal["v1"] = "v1"


class BotStaffContextResponse(BaseModel):
    telegram_id: int = Field(ge=1)
    is_staff: bool = False
    display_name: str = ""
    primary_role: str = ""
    roles: list[str] = Field(default_factory=list)
    legacy_installer_id: int | None = None
    is_manager: bool = False
    is_executor: bool = False
