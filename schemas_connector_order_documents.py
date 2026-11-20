"""MCP entries for scoped document discovery, diagnostics and external file intake."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from modules.documents.application.external_order_documents import (
    ExternalDocumentFileRole,
    ExternalDocumentStatus,
    ExternalOrderDocumentPayload,
)
from schemas_connector_maintenance import OpenAIFile
from schemas_connector_mcp import OrderIdInput, WriteInput
from schemas_order_diagnostics import PrepareOrderTechnicalActPayload


class OrderDocumentsListInput(OrderIdInput):
    document_type: str | None = Field(default=None, min_length=1, max_length=64)
    site_id: int | None = Field(default=None, gt=0)
    equipment_id: int | None = Field(default=None, gt=0)
    limit: int = Field(default=30, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class OrderDocumentSummary(BaseModel):
    order_id: int
    document_id: int
    document_type: str
    origin: Literal["native_generated", "external_upload", "legacy"]
    status: str | None
    external_status: ExternalDocumentStatus | None
    number: str | None
    document_date: date
    proposal_id: int | None
    base_document_id: int | None
    base_customer_contract_id: int | None
    site_ids: list[int]
    equipment_ids: list[int]
    revision: str | None
    file_version: int
    manager_url: str


class OrderDocumentsListResult(BaseModel):
    items: list[OrderDocumentSummary]
    total: int
    has_more: bool
    manager_url: str
    upload_manager_url: str


class OrderExternalDocumentSaved(BaseModel):
    order_id: int
    document_id: int
    document_type: str
    origin: Literal["native_generated", "external_upload", "legacy"]
    external_status: ExternalDocumentStatus | None
    file_version: int
    manager_url: str


class UploadOrderDocumentInput(OrderIdInput, WriteInput):
    payload: ExternalOrderDocumentPayload
    file: OpenAIFile | None = None


class RegisterExternalOrderContractPayload(ExternalOrderDocumentPayload):
    document_type: Literal["contract"] = "contract"


class RegisterExternalOrderContractInput(OrderIdInput, WriteInput):
    payload: RegisterExternalOrderContractPayload
    file: OpenAIFile | None = None
    metadata_only: bool = False


class AttachOrderDocumentFileInput(OrderIdInput, WriteInput):
    document_id: int = Field(gt=0)
    file_role: ExternalDocumentFileRole
    expected_version: int = Field(ge=0)
    file: OpenAIFile | None = None


class PrepareOrderInspectionActInput(PrepareOrderTechnicalActPayload, OrderIdInput):
    site_id: int = Field(gt=0)
    document_type: Literal["technical_inspection_act"] = "technical_inspection_act"


class PrepareOrderDefectActInput(PrepareOrderTechnicalActPayload, OrderIdInput):
    site_id: int = Field(gt=0)
    document_type: Literal["defect_act"] = "defect_act"
