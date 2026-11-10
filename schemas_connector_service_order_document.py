"""Connector contract for native service-order document drafts."""

from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from modules.documents.api.schemas import DocumentCustomerReadiness, ConsumerDocumentTermsPayload
from schemas_connector_mcp import ConnectorInput, WriteInput


class ServiceOrderContractPrepareInput(WriteInput):
    order_id: int = Field(gt=0)
    proposal_id: int = Field(gt=0)
    expected_version: str = Field(min_length=1, max_length=128)
    legal_entity_id: int | None = Field(default=None, gt=0)
    document_type: Literal["contract", "invoice", "b2c_customer_equipment_installation_act",
        "b2c_maintenance_repair_act", "b2c_supply_installation_act", "b2c_route_laying_act"] = "contract"
    consumer_terms: ConsumerDocumentTermsPayload | None = None
    replaces_document_id: int | None = Field(default=None, gt=0)
    expected_document_revision: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")
    business_role: Literal["payment_request", "offer"] | None = None
    issue_date: date
    template_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_role(self):
        if self.document_type == "invoice" and self.business_role is None:
            raise ValueError("Choose invoice role: offer (invoice-contract) or payment_request")
        if self.document_type != "invoice" and self.business_role is not None:
            raise ValueError("Invoice role is only available for invoices")
        if self.consumer_terms is not None and not self.document_type.startswith("b2c_"):
            raise ValueError("Consumer terms require a consumer document type")
        if self.replaces_document_id is not None and self.expected_document_revision is None:
            raise ValueError("Read the source document revision before preparing a replacement")
        return self


class ServiceOrderContractReadInput(ConnectorInput):
    document_id: int = Field(gt=0)


class ConsumerDocumentsListInput(ConnectorInput):
    order_id: int = Field(gt=0)
    limit: int = Field(default=30, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ConsumerDocumentSummary(BaseModel):
    document_id: int
    order_id: int
    proposal_id: int | None
    legal_entity_id: int | None
    document_type: str
    status: str
    issue_date: date
    replaces_document_id: int | None
    manager_url: str


class ConsumerDocumentsListResult(BaseModel):
    items: list[ConsumerDocumentSummary]
    total: int
    has_more: bool


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
    consumer_terms: ConsumerDocumentTermsPayload | None = None
    equipment_id: int | None = None
    document_revision: str
    inherits_source_snapshot: bool = False
