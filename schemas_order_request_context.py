"""Read-only source evidence, separate from the editable order comment."""

from pydantic import BaseModel, Field

from schemas import ManagerServiceAttachmentItemResponse


class OrderRequestSourceText(BaseModel):
    label: str
    text: str
    truncated: bool = False
    url: str | None = None


class OrderRequestFile(ManagerServiceAttachmentItemResponse):
    # Positive IDs use service-attachment access; negative IDs are saved mail files.
    mail_message_id: int | None = None
    mail_attachment_id: int | None = None
    available: bool = True
    origin_label: str


class ManagerOrderRequestContext(BaseModel):
    sources: list[OrderRequestSourceText] = Field(default_factory=list)
    files: list[OrderRequestFile] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
