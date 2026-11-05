"""Connector contract for native service-order document drafts."""

from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from modules.documents.api.schemas import DocumentCustomerReadiness
from schemas_connector_mcp import ConnectorInput, WriteInput


class ServiceOrderContractPrepareInput(WriteInput):
    order_id: int = Field(gt=0)
    proposal_id: int = Field(gt=0)
    expected_version: str = Field(min_length=1, max_length=128)
    legal_entity_id: int | None = Field(default=None, gt=0)
    document_type: Literal["contract", "invoice"] = "contract"
    business_role: Literal["payment_request", "offer"] | None = None
    issue_date: date
    template_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_role(self):
        if self.document_type == "invoice" and self.business_role is None:
            raise ValueError("Choose invoice role: offer (invoice-contract) or payment_request")
        if self.document_type == "contract" and self.business_role is not None:
            raise ValueError("Invoice role is only available for invoices")
        return self


class ServiceOrderContractReadInput(ConnectorInput):
    document_id: int = Field(gt=0)


class ServiceOrderContractResult(BaseModel):
    order_id: int
    proposal_id: int
    document_id: int
    legal_entity_id: int
    document_type: str
    business_role: str | None
    status: str
    proposal_version: str | None
    current_proposal_version: str | None
    stale: bool
    customer_ready_and_current: bool
    readiness: DocumentCustomerReadiness
    total_byn: str
    vat_label: str
    manager_url: str
    payment_terms: str | None = None
