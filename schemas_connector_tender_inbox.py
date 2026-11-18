"""Read-only Kitlane MCP tender inbox contract."""

from datetime import datetime
import re
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from models import OrderStatus
from schemas_connector_mcp import ConnectorInput
from services.belzakupki_canonical_identity import canonical_procurement_url


class TenderInboxInput(ConnectorInput):
    source: Literal["belzakupki"] = "belzakupki"
    status: OrderStatus | None = Field(
        default=None, description="CRM status. The default unarchived view shows new_lead orders."
    )
    archived: bool | None = Field(
        default=False, description="False for unarchived, true for the archive, null for both."
    )
    unread: bool | None = Field(default=None, description="Personal read state for the connected manager.")
    region: str | None = Field(
        default=None, min_length=1, max_length=120,
        description="Literal case-insensitive fragment of a stored tender region, location or order delivery address.",
    )
    procedure: str | None = Field(
        default=None, min_length=1, max_length=2048,
        description="Exact supported canonical procedure URL or a Goszakupki auc-prefixed procedure ID.",
    )
    deadline_from: AwareDatetime | None = Field(default=None, description="Inclusive effective deadline lower bound.")
    deadline_to: AwareDatetime | None = Field(default=None, description="Inclusive effective deadline upper bound.")
    current_only: bool = Field(
        default=False, description="Require a known effective deadline that has not passed."
    )
    sort: Literal["newest", "deadline"] = "newest"
    page: int = Field(default=1, ge=1, le=1_000_000)
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("region")
    @classmethod
    def clean_region(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Region must not be blank")
        return value

    @field_validator("procedure")
    @classmethod
    def clean_procedure(cls, value: str | None) -> str | None:
        if value is None:
            return None
        canonical = canonical_procurement_url(value)
        if canonical:
            return canonical
        numeric = re.fullmatch(r"auc0*([1-9][0-9]{0,17})", value.strip(), flags=re.IGNORECASE)
        if numeric:
            return f"auc{numeric[1]}"
        raise ValueError("Use a supported canonical procedure URL or a Goszakupki auc-prefixed procedure ID")

    @model_validator(mode="after")
    def validate_deadline_range(self):
        if self.deadline_from is not None and self.deadline_to is not None and self.deadline_from > self.deadline_to:
            raise ValueError("deadline_from must not be later than deadline_to")
        return self


class TenderSourceReference(BaseModel):
    source_reference: str = Field(description="Scoped reference for previewing documents from this source.")
    source_code: str
    external_id: str
    source_url: str | None
    canonical_conflict: bool = False


class TenderInboxItem(BaseModel):
    order_id: int
    manager_url: str
    status: OrderStatus
    title: str | None
    customer_name: str | None
    created_at: datetime
    unread: bool
    archived: bool
    archive_outcome: str | None
    region: str | None
    location: str | None
    estimated_budget: float | None
    budget_currency: str | None
    quantity: float | None
    source: Literal["belzakupki"] = "belzakupki"
    source_code: str | None
    external_id: str | None
    provider_tender_id: str | None
    source_url: str | None
    canonical_url: str | None = Field(description="Verified procedure identity shared by source mirrors.")
    canonical_external_id: str | None
    source_references: list[TenderSourceReference]
    source_references_truncated: bool
    canonical_conflict: bool
    procedure_kind: str | None = Field(description="Stored or identified by the verified procedure URL.")
    participation_method: str | None = Field(description="Explicit source evidence, when stored.")
    published_at: AwareDatetime | None
    source_updated_at: AwareDatetime | None
    deadline_at: AwareDatetime | None = Field(description="Effective deadline used for inbox filtering.")
    deadline_basis: Literal["workflow", "submission", "confirmed_tender"] | None
    source_deadline_at: AwareDatetime | None = Field(description="Latest date reported by the selected source.")
    source_deadline_kind: str | None
    original_source_deadline_at: AwareDatetime | None = Field(
        description="Earliest earlier submission deadline retained for the selected native source, if known."
    )
    previous_source_deadline_at: AwareDatetime | None = Field(
        description="Latest earlier differing submission deadline retained for the selected native source, if known."
    )


class TenderInboxResult(BaseModel):
    items: list[TenderInboxItem]
    page: int
    limit: int
    total: int
    has_more: bool
    as_of: AwareDatetime
