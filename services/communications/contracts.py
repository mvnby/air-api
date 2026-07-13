from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _ContractV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class IntegrationEventEnvelopeV1(_ContractV1):
    event_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    event_type: str = Field(
        min_length=3,
        max_length=120,
        pattern=r"^[a-z][a-z0-9_.-]+$",
    )
    schema_version: Literal[1] = 1
    aggregate_type: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    )
    aggregate_id: str = Field(min_length=1, max_length=128)
    aggregate_version: int | None = Field(default=None, ge=0)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor_id: str | None = Field(default=None, max_length=128)
    correlation_id: str | None = Field(default=None, max_length=128)
    causation_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    payload: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value


class PublicOrderCustomerSnapshotV1(_ContractV1):
    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=1, max_length=80)
    email: str | None = Field(default=None, max_length=254)
    address: str | None = Field(default=None, max_length=500)
    customer_type: Literal["individual", "company"] = "individual"


class PublicOrderProductLineSnapshotV1(_ContractV1):
    product_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=180)
    quantity: int = Field(ge=1, le=20)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    installation_included: bool = False
    installation_price: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=14,
        decimal_places=2,
    )


class PublicOrderServiceLineSnapshotV1(_ContractV1):
    service_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=180)
    quantity: int = Field(ge=1, le=20)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class PublicOrderCreatedPayloadV1(_ContractV1):
    order_id: int = Field(gt=0)
    status: str = Field(min_length=1, max_length=40)
    customer: PublicOrderCustomerSnapshotV1
    comment: str | None = Field(default=None, max_length=2000)
    total_amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: Literal["BYN"] = "BYN"
    product_lines: list[PublicOrderProductLineSnapshotV1] = Field(
        default_factory=list,
        max_length=20,
    )
    service_lines: list[PublicOrderServiceLineSnapshotV1] = Field(
        default_factory=list,
        max_length=20,
    )


class PublicContactLeadCreatedPayloadV1(_ContractV1):
    lead_id: int = Field(gt=0)
    status: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=1, max_length=80)
    email: str | None = Field(default=None, max_length=254)
    address: str | None = Field(default=None, max_length=500)
    message: str | None = Field(default=None, max_length=2000)
