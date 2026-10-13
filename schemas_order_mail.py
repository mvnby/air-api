"""Order context is optional content when preparing a saved mail draft."""

from pydantic import BaseModel, ConfigDict, Field


class MailOrderDraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_email: str = Field(default="", max_length=4096)
    subject: str = Field(default="", max_length=998)
    body_text: str | None = Field(default=None, max_length=100_000)
    body_html: str | None = Field(default=None, max_length=100_000)
    reply_to: str | None = Field(default=None, max_length=254)
    document_ids: list[int] = Field(default_factory=list, max_length=10)
    registration_certificate_id: str | None = Field(default=None, min_length=32, max_length=32)
    legal_entity_id: int | None = Field(default=None, gt=0)
