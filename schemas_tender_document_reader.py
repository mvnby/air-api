"""Read-only evidence from a single original tender document."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TenderDocumentReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: int = Field(gt=0)
    document_id: str = Field(min_length=1, max_length=300)
    offset: int = Field(default=0, ge=0, le=180000)
    limit: int = Field(default=10000, ge=1, le=16000)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_reference: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_offset(self):
        if self.offset and self.sha256 is None:
            raise ValueError("Для продолжения укажите SHA-256 из предыдущего ответа.")
        return self


class TenderDocumentFragment(BaseModel):
    page: int | None = None
    fragment: int
    offset: int
    text: str
    method: Literal["embedded", "ocr", "docx", "doc"]
    section: str | None = None


class TenderDocumentReadResult(BaseModel):
    order_id: int
    document_id: str
    filename: str | None = None
    mime_type: str | None = None
    sha256: str | None = None
    source_reference: str | None = None
    origin: Literal["source", "saved_original"] | None = None
    attachment_id: int | None = None
    status: Literal["complete", "partial", "unreadable", "unsupported", "oversized", "unavailable"]
    diagnostics: list[str] = Field(default_factory=list)
    fragments: list[TenderDocumentFragment] = Field(default_factory=list)
    offset: int = 0
    next_offset: int | None = None
    total_chars: int = 0
