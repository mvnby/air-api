"""Shared Manager/MCP contracts for saved mail and exact-version sending."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from services.mail_headers import valid_message_id


class MailThreadPayload(BaseModel):
    in_reply_to: str | None = Field(default=None, max_length=998)
    references: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("in_reply_to")
    @classmethod
    def validate_parent(cls, value):
        if value is not None and not valid_message_id(value):
            raise ValueError("Invalid In-Reply-To message identifier")
        return value

    @field_validator("references")
    @classmethod
    def validate_references(cls, values):
        if any(not valid_message_id(value) for value in values):
            raise ValueError("Invalid References message identifier")
        return list(dict.fromkeys(values))


class MailDraftCreatePayload(MailThreadPayload):
    model_config = ConfigDict(extra="forbid")
    account_id: str = Field(default="system", max_length=64)
    to: list[str] = Field(default_factory=list, max_length=50)
    cc: list[str] = Field(default_factory=list, max_length=50)
    bcc: list[str] = Field(default_factory=list, max_length=50)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=100_000)
    order_id: int | None = Field(default=None, ge=1)
    customer_id: int | None = Field(default=None, ge=1)


class MailDraftUpdatePayload(MailThreadPayload):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    account_id: str | None = Field(default=None, max_length=64)
    to: list[str] | None = Field(default=None, max_length=50)
    cc: list[str] | None = Field(default=None, max_length=50)
    bcc: list[str] | None = Field(default=None, max_length=50)
    subject: str | None = Field(default=None, max_length=998)
    body_text: str | None = Field(default=None, max_length=100_000)
    order_id: int | None = Field(default=None, ge=1)
    customer_id: int | None = Field(default=None, ge=1)


class MailVersionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class MailConfirmPayload(MailVersionPayload):
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class MailAttachmentResponse(BaseModel):
    id: int | None = None
    filename: str
    mime_type: str = "application/octet-stream"
    size: int = 0
    sha256: str | None = None
    available: bool = False
    download_url: str | None = None


class MailMessageResponse(BaseModel):
    id: int
    version: int
    status: str
    folder: Literal["inbox", "outbox", "drafts"]
    account_id: str = "system"
    sender_email: str | None = None
    sender_name: str | None = None
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str = ""
    body_text: str = ""
    attachments: list[MailAttachmentResponse] = Field(default_factory=list)
    order_id: int | None = None
    customer_id: int | None = None
    manager_url: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    sent_at: datetime | None = None
    confirmed_version: int | None = None
    content_hash: str | None = None
    csrf_token: str | None = None
    message_id: str | None = None
    reply_to: list[str] = Field(default_factory=list)
    in_reply_to: str | None = None
    references: list[str] = Field(default_factory=list)
    delivery_projection_pending: bool = False


class MailMessageListResponse(BaseModel):
    items: list[MailMessageResponse] = Field(description="Saved mail summaries; body_text contains at most 300 characters. Read message detail/preview for full content and approval hash.")
    total: int
    page: int
    limit: int


class MailAccountResponse(BaseModel):
    id: str
    email: str
    name: str
    signature: str = ""


class MailAccountListResponse(BaseModel):
    items: list[MailAccountResponse]


class MailTextSuggestionResponse(BaseModel):
    version: int
    subject: str
    body_text: str
