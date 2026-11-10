"""Structured issuer tax facts saved with document requisites."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IssuerTaxProfile(BaseModel):
    """User-maintained facts for document review, not legal certification."""

    model_config = ConfigDict(extra="forbid")

    regime: str | None = Field(default=None, max_length=200)
    vat_basis: str | None = Field(default=None, max_length=1000)
    effective_from: date | None = Field(
        default=None,
        description="Date from which this profile is used for documents; not necessarily the regime start date.",
    )
    verified_at: date | None = None
    official_source: str | None = Field(default=None, max_length=1000)
    confirmation_basis: str | None = Field(default=None, max_length=1000)

    @field_validator("official_source")
    @classmethod
    def validate_official_source(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip()
        parsed = urlparse(normalized)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Источник должен быть ссылкой HTTPS")
        return normalized
