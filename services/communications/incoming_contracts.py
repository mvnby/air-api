"""Snapshot contract for new incoming requests outside website workflows."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TENANT_INCOMING_CREATED_EVENT = "tenant.incoming.created"
TENANT_INCOMING_TEMPLATE_KEY = "telegram.tenant_incoming_created"


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
