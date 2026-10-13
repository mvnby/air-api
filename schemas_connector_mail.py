"""Mail MCP inputs: saved versions, separate sends, no agent-supplied consent."""

from typing import Literal

from pydantic import Field, field_validator

from schemas_connector_maintenance import OpenAIFile
from schemas_connector_mcp import ConnectorInput, WriteInput
from schemas_mail import MailDraftCreatePayload, MailDraftUpdatePayload


class MailSearchInput(ConnectorInput):
    folder: Literal["inbox", "outbox", "drafts"] = "inbox"
    q: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=40)
    order_id: int | None = Field(default=None, gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    page: int = Field(default=1, ge=1, le=10000)
    limit: int = Field(default=20, ge=1, le=50)


class MailMessageInput(ConnectorInput):
    # Incoming message IDs are negative, outgoing/draft IDs are positive.
    message_id: int

    @field_validator("message_id")
    @classmethod
    def nonzero_id(cls, value: int) -> int:
        if value == 0:
            raise ValueError("Message ID must be nonzero")
        return value


class MailDraftInput(ConnectorInput):
    draft_id: int = Field(gt=0)


class MailDraftCreateInput(WriteInput):
    payload: MailDraftCreatePayload


class MailDraftUpdateInput(WriteInput):
    draft_id: int = Field(gt=0)
    payload: MailDraftUpdatePayload


class MailDraftVersionInput(WriteInput):
    draft_id: int = Field(gt=0)
    expected_version: int = Field(ge=1)


class MailDraftAttachmentInput(MailDraftVersionInput):
    file: OpenAIFile
