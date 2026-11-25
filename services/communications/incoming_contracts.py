"""Snapshot contract for new incoming requests outside website workflows."""

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from services.belzakupki_canonical_identity import canonical_procurement_url


TENANT_INCOMING_CREATED_EVENT = "tenant.incoming.created"
TENANT_INCOMING_TEMPLATE_KEY = "telegram.tenant_incoming_created"


class TenderCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=300)
    source_label: str = Field(min_length=1, max_length=80)
    source_url: str | None = Field(default=None, max_length=2048)
    reference: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=200)
    deadline_at: AwareDatetime | None = None
    quantity: str | None = Field(default=None, max_length=80)
    budget_amount: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    budget_currency: str | None = Field(default=None, max_length=12)
    status: Literal["recommend", "review", "skip"]
    reason: str = Field(min_length=1, max_length=180)
    prior_event_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")

    @model_validator(mode="after")
    def validate_links(self):
        if self.source_url and canonical_procurement_url(self.source_url) != self.source_url:
            raise ValueError("Tender source must be a canonical procurement URL")
        if self.prior_event_id and self.status != "recommend":
            raise ValueError("Only a recommendation can update a tender card")
        return self


class TenantIncomingCreatedPayloadV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: int = Field(gt=0)
    storefront_id: int = Field(gt=0)
    entity_type: Literal["lead", "order"]
    entity_id: int = Field(gt=0)
    source: str = Field(min_length=1, max_length=40)
    name: str | None = Field(default=None, max_length=240)
    phone: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=254)
    request_text: str = Field(max_length=12000)
    subject: str | None = Field(default=None, max_length=300)
    tender: TenderCard | None = None
