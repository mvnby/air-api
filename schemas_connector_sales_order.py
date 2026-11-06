"""Explicit chosen sales composition and resumable native draft contracts."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.documents.api.schemas import DocumentCustomerReadiness
from schemas import ManagerCustomerCreatePayload
from schemas_connector_mcp import ConnectorInput, WriteInput
from schemas_connector_sales_pricing import SalesInstallationInput


class SalesNewCustomer(ManagerCustomerCreatePayload):
    model_config = ConfigDict(extra="forbid")
    type: Literal["individual", "company", "individual_entrepreneur"]
    name: str = Field(min_length=1, max_length=300)


class SalesCustomerCreateInput(WriteInput):
    customer: SalesNewCustomer


class SalesCustomerResult(BaseModel):
    customer_id: int
    name: str
    customer_type: str
    manager_url: str


class SalesOrderSaveInput(WriteInput):
    product_id: int = Field(gt=0)
    installation: SalesInstallationInput
    accessory_product_ids: list[int] = Field(default_factory=list, max_length=20)
    expected_calculation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    customer_id: int = Field(gt=0)
    order_id: int | None = Field(default=None, gt=0)
    proposal_id: int | None = Field(default=None, gt=0)
    expected_version: str | None = Field(default=None, max_length=128)
    request_text: str = Field(min_length=1, max_length=20000)
    requirements_text: str | None = Field(default=None, max_length=10000)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def explicit_target(self):
        if len(set(self.accessory_product_ids)) != len(self.accessory_product_ids) or any(i <= 0 for i in self.accessory_product_ids):
            raise ValueError("Accessory IDs must be distinct positive IDs")
        if any(v is not None for v in (self.order_id, self.proposal_id, self.expected_version)):
            if not all(v is not None for v in (self.order_id, self.proposal_id, self.expected_version)):
                raise ValueError("Edits require order_id, proposal_id and expected_version together")
        return self


class SalesOrderReadInput(ConnectorInput):
    order_id: int = Field(gt=0)
    proposal_id: int | None = Field(default=None, gt=0)


class SalesOrderLine(BaseModel):
    id: int
    product_id: int | None = None
    title: str
    quantity: int
    unit_price_byn: Decimal
    total_byn: Decimal
    installation_estimate_revision_id: int | None = None


class SalesOrderResult(BaseModel):
    order_id: int
    customer_id: int
    customer_type: str
    proposal_id: int
    status: str
    proposal_status: str
    workflow_type: str
    service_type: str
    version: str
    request_text: str | None
    requirements_text: str | None
    title: str | None
    address: str | None
    saved_selection: dict | None
    products: list[SalesOrderLine]
    services: list[SalesOrderLine]
    equipment_total_byn: Decimal
    accessories_total_byn: Decimal
    installation_total_byn: Decimal
    total_byn: Decimal
    currency: Literal["BYN"] = "BYN"
    manager_url: str


class SalesOrderOfferPrepareInput(WriteInput):
    order_id: int = Field(gt=0)
    proposal_id: int = Field(gt=0)
    expected_version: str = Field(min_length=1, max_length=128)
    legal_entity_id: int | None = Field(default=None, gt=0)
    issue_date: date
    template_id: int | None = Field(default=None, gt=0)


class SalesOrderOfferReadInput(ConnectorInput):
    document_id: int = Field(gt=0)


class SalesOrderOfferResult(BaseModel):
    order_id: int
    proposal_id: int
    document_id: int
    legal_entity_id: int
    document_type: Literal["offer"] = "offer"
    status: str
    proposal_version: str
    current_proposal_version: str
    stale: bool
    customer_ready_and_current: bool
    readiness: DocumentCustomerReadiness
    total_byn: str
    manager_url: str
