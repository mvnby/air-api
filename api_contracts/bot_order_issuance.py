"""Official issuance of a saved order document."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


BotDocumentRevision = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64)]


class BotIssueDocument(BaseModel, extra="forbid"):
    kind: Literal["issue_document"]
    document_id: int = Field(gt=0, le=2**31 - 1, strict=True)
    expected_document_revision: BotDocumentRevision
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def require_explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Подтвердите официальный выпуск документа")
        return value


class BotOrderIssuance(BaseModel):
    document_id: int
    state: Literal["ready", "reserved", "blocked", "issued"]
    revision: BotDocumentRevision | None
    reason: str | None
    document_type: str
    legal_entity_name: str | None
    can_download_pdf: bool
