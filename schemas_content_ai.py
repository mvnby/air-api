"""Typed request/response contracts for Manager content draft generation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ContentDraftMode = Literal["from_source", "polish_text"]


class _ContentDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ContentDraftMode
    source_url: str | None = Field(default=None, max_length=2048)
    full_description: str | None = Field(default=None, max_length=50_000)

    @model_validator(mode="after")
    def validate_mode_input(self):
        if self.mode == "from_source":
            if not str(self.source_url or "").strip():
                raise ValueError("source_url is required for from_source mode")
            if self.full_description is not None:
                raise ValueError("full_description is not accepted in from_source mode")
        else:
            if not str(self.full_description or "").strip():
                raise ValueError("full_description is required for polish_text mode")
            if self.source_url is not None:
                raise ValueError("source_url is not accepted in polish_text mode")
        return self


class FeatureContentDraftRequest(_ContentDraftRequest):
    """Only immutable context and source text are sent; entity fields are never saved."""

    name: str | None = Field(default=None, max_length=200)
    brand_name: str | None = Field(default=None, max_length=200)
    category_name: str | None = Field(default=None, max_length=200)


class ProductSeriesContentDraftRequest(_ContentDraftRequest):
    """Series identity is grounding context, not a generated output field."""

    title: str | None = Field(default=None, max_length=200)
    brand_name: str | None = Field(default=None, max_length=200)


class BrandShortDescriptionDraftRequest(BaseModel):
    """Brand identity and source copy are immutable draft context."""

    model_config = ConfigDict(extra="forbid")

    brand_name: str | None = Field(default=None, max_length=200)
    full_description: str = Field(min_length=1, max_length=50_000)

    @model_validator(mode="after")
    def validate_description(self):
        if not self.full_description.strip():
            raise ValueError("full_description is required")
        return self


class FeatureContentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    short_description: str = Field(min_length=1, max_length=700)
    full_description: str = Field(min_length=1, max_length=12_000)
    footnote: str | None = Field(default=None, max_length=700)
    seo_title: str | None = Field(default=None, max_length=68)
    seo_description: str | None = Field(default=None, max_length=158)
    prompt_version: str


class ProductSeriesContentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tagline: str | None = Field(default=None, max_length=160)
    short_description: str = Field(min_length=1, max_length=700)
    description: str = Field(min_length=1, max_length=16_000)
    seo_title: str | None = Field(default=None, max_length=68)
    seo_description: str | None = Field(default=None, max_length=158)
    prompt_version: str


class BrandShortDescriptionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    short_description: str = Field(min_length=1, max_length=200)
    prompt_version: str
