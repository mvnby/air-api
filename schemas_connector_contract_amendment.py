"""MCP inputs reuse the native domain's typed commercial work and conditions."""

from datetime import date
from pydantic import BaseModel, Field
from schemas_connector_mcp import ConnectorInput, WriteInput
from modules.documents.domain.contract_amendment import ContractAmendmentTerms
from modules.documents.api.amendment_schemas import (
    AmendmentBasisList as AmendmentBasisList,
)
from modules.documents.api.schemas import DocumentCustomerReadiness


class ContractBasisInput(ConnectorInput):
    order_id: int = Field(gt=0)


class ContractAmendmentPrepareInput(WriteInput):
    order_id: int = Field(gt=0)
    base_document_id: int = Field(gt=0)
    expected_basis_revision: str = Field(pattern="^[a-f0-9]{64}$")
    issue_date: date
    amendment_terms: ContractAmendmentTerms
    template_id: int | None = Field(default=None, gt=0)


class ContractAmendmentReadInput(ConnectorInput):
    document_id: int = Field(gt=0)


class ContractAmendmentResult(BaseModel):
    order_id: int
    base_document_id: int
    document_id: int
    status: str
    revision: str
    basis_revision: str
    current_basis_revision: str
    stale: bool
    original_amount: str
    other_amendments_amount: str
    change_amount: str
    new_total: str
    currency: str
    amendment_terms: ContractAmendmentTerms
    readiness: DocumentCustomerReadiness
    manager_url: str
