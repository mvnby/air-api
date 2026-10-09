"""Bounded native opportunity contract for server-to-server tender intake."""

import json
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, StrictBool, field_validator, model_validator

PositiveID = Annotated[int, Field(strict=True, gt=0, le=9223372036854775807)]


class IntakeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TenderProfile(IntakeModel):
    id: PositiveID
    name: str = Field(max_length=500)


class NativeTender(IntakeModel):
    id: PositiveID | None = None
    source: str = Field(min_length=1, max_length=100)
    external_id: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=1000)
    customer_name: str | None = Field(default=None, max_length=1000)
    url: str | None = Field(default=None, max_length=2048)
    deadline_at: AwareDatetime | None = None
    deadline_kind: str = Field(default="submission", max_length=40)
    published_at: AwareDatetime | None = None
    estimated_value: Annotated[float, Field(allow_inf_nan=False, ge=0)] | None = None
    currency: str | None = Field(default=None, max_length=12)
    location: str | None = Field(default=None, max_length=1000)
    quantity: Annotated[float, Field(allow_inf_nan=False, ge=0)] | None = None
    summary: str | None = Field(default=None, max_length=4000)
    contacts: list[dict[str, JsonValue]] | None = Field(default=None, max_length=100)
    ai_analysis: dict[str, JsonValue] | None = None

    @field_validator("source", "external_id", "title")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = urlsplit(value)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or any(char.isspace() or ord(char) < 32 for char in value)):
                raise ValueError("invalid source URL")
            _ = parsed.port
        except ValueError:
            raise ValueError("source URL must be HTTP(S) without credentials") from None
        return value


class NativeOpportunity(IntakeModel):
    id: PositiveID
    profile: TenderProfile
    score: Annotated[float, Field(allow_inf_nan=False)] | None = None
    relevance_status: str = Field(min_length=1, max_length=40)
    eligible: StrictBool
    reason: str | None = Field(default=None, max_length=4000)
    updated_at: AwareDatetime
    ai_analysis: dict[str, JsonValue] | None = None
    tender: NativeTender

    @model_validator(mode="after")
    def bounded_payload(self):
        try:
            serialized = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, allow_nan=False)
        except ValueError:
            raise ValueError("source evidence must contain finite JSON values") from None
        if len(serialized.encode("utf-8")) > 65536:
            raise ValueError("opportunity exceeds 64 KiB")
        return self


class TenderLeadPushResult(IntakeModel):
    order_id: int | None
    outcome: Literal["created", "updated", "unchanged", "skipped"]
    source: str
    external_id: str
