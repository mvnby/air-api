"""Shared Manager/MCP contracts for saved mail and exact-version sending."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MailDraftCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str = Field(default="system", max_length=64)
    to: list[str] = Field(default_factory=list, max_length=50)
    cc: list[str] = Field(default_factory=list, max_length=50)
    bcc: list[str] = Field(default_factory=list, max_length=50)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=100_000)
    order_id: int | None = Field(default=None, ge=1)
    customer_id: int | None = Field(default=None, ge=1)


class MailDraftUpdatePayload(BaseModel):
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


class MailMessageListResponse(BaseModel):
    items: list[MailMessageResponse]
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
