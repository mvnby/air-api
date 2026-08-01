from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


TenantOfferStatus = Literal["active", "disabled"]
POSTGRESQL_INTEGER_MAX = 2_147_483_647


class TenantOfferPricing(BaseModel):
    price: int = Field(ge=0, le=POSTGRESQL_INTEGER_MAX)
    old_price: int | None = Field(
        default=None,
        ge=0,
        le=POSTGRESQL_INTEGER_MAX,
    )

    @model_validator(mode="after")
    def validate_old_price(self):
        if self.old_price is not None and self.old_price < self.price:
            raise ValueError("old_price must be greater than or equal to price")
        return self


class ManagerTenantOfferUpsert(TenantOfferPricing):
    product_id: int = Field(gt=0, le=POSTGRESQL_INTEGER_MAX)
    is_published: bool = False
    status: TenantOfferStatus = "active"


class ManagerTenantOfferUpdate(BaseModel):
    # These fields may be omitted, but explicit null is not a valid command.
    # Keeping the annotation non-null also exposes the correct optional-but-not-
    # nullable contract in OpenAPI. ``exclude_unset=True`` distinguishes an
    # omitted field from the default used only to build the partial model.
    price: int = Field(default=None, ge=0, le=POSTGRESQL_INTEGER_MAX)
    old_price: int | None = Field(
        default=None,
        ge=0,
        le=POSTGRESQL_INTEGER_MAX,
    )
    is_published: bool = Field(default=None)
    status: TenantOfferStatus = Field(default=None)


class ManagerTenantOfferResponse(BaseModel):
    id: int
    storefront_id: int
    product_id: int
    product_title: str
    product_slug: str
    price: int
    old_price: int | None = None
    is_published: bool
    status: TenantOfferStatus
    created_by_username: str
    updated_by_username: str
    created_at: datetime
    updated_at: datetime


class ManagerTenantOfferListResponse(BaseModel):
    items: list[ManagerTenantOfferResponse] = Field(default_factory=list)
    total: int


class ManagerTenantAuditEventResponse(BaseModel):
    id: int
    storefront_id: int
    actor_staff_user_id: int | None = None
    actor_username: str
    action: str
    entity_type: str
    entity_id: int
    request_id: str
    change_set: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ManagerTenantAuditEventListResponse(BaseModel):
    items: list[ManagerTenantAuditEventResponse] = Field(default_factory=list)
    total: int
