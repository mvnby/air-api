"""Bounded MCP maintenance inputs; actor and workspace are server-owned."""
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from api_contracts.maintenance_observations import (
    MaintenanceActSelectedObservation, MaintenanceDefectActItem,
    MaintenanceObservationContent, MaintenanceObservationItem, UpdateMaintenanceObservation,
)
from api_contracts.maintenance_offers import MaintenanceOfferLine, MaintenanceOfferList
from schemas import ManagerServiceAttachmentItemResponse
from schemas_connector_mcp import ConnectorInput, WriteInput


class EquipmentIdInput(ConnectorInput):
    equipment_id: int = Field(gt=0)


class EquipmentListInput(ConnectorInput):
    customer_id: int = Field(gt=0)
    customer_branch_id: int | None = Field(default=None, gt=0)
    page: int = Field(default=1, ge=1, le=10000)
    limit: int = Field(default=20, ge=1, le=50)
    include_archived: bool = False


class EquipmentHistoryInput(EquipmentIdInput):
    page: int = Field(default=1, ge=1, le=10000)
    limit: int = Field(default=20, ge=1, le=50)


class MaintenanceOrderListInput(ConnectorInput):
    order_id: int = Field(gt=0)
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=10000)


class FindingListInput(ConnectorInput):
    order_id: int | None = Field(default=None, gt=0)
    equipment_id: int | None = Field(default=None, gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    branch_id: int | None = Field(default=None, gt=0)
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=10000)

    @model_validator(mode="after")
    def one_context(self):
        if sum(value is not None for value in (self.order_id, self.equipment_id, self.customer_id)) != 1:
            raise ValueError("Select exactly one order, equipment or customer")
        if self.branch_id is not None and self.customer_id is None:
            raise ValueError("Object filtering requires a customer")
        return self


class FindingIdInput(ConnectorInput):
    observation_id: int = Field(gt=0)


class CreateFindingPayload(MaintenanceObservationContent):
    original_comment: str = Field(min_length=1, max_length=10000)
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def observed_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Observed time requires a timezone")
        return value


class FindingCreateInput(WriteInput):
    order_id: int = Field(gt=0)
    payload: CreateFindingPayload


class FindingUpdateInput(WriteInput):
    observation_id: int = Field(gt=0)
    payload: UpdateMaintenanceObservation


class DefectActPayload(ConnectorInput):
    observations: list[MaintenanceActSelectedObservation] = Field(min_length=1, max_length=100)
    legal_entity_id: int = Field(gt=0)
    issue_date: date
    replaces_document_id: int | None = Field(default=None, gt=0)

    @field_validator("observations")
    @classmethod
    def selected(cls, values):
        if len({row.observation_id for row in values}) != len(values):
            raise ValueError("Select each finding once")
        return sorted(values, key=lambda row: row.observation_id)


class DefectActPrepareInput(WriteInput):
    order_id: int = Field(gt=0)
    payload: DefectActPayload


class OfferPayload(ConnectorInput):
    proposal_id: int = Field(gt=0)
    lines: list[MaintenanceOfferLine] = Field(min_length=1, max_length=100)

    @field_validator("lines")
    @classmethod
    def selected(cls, values):
        if len({(row.kind, row.line_id) for row in values}) != len(values):
            raise ValueError("Map each proposal line once")
        return sorted(values, key=lambda row: (row.kind, row.line_id))


class OfferPrepareInput(WriteInput):
    order_id: int = Field(gt=0)
    payload: OfferPayload


class OpenAIFile(ConnectorInput):
    # Required/optional properties follow the official ChatGPT fileParams contract.
    download_url: str = Field(min_length=1, max_length=8192)
    file_id: str = Field(min_length=6, max_length=200, pattern=r"^file[-_][A-Za-z0-9_-]+$")
    mime_type: str = Field(default="", max_length=100)
    file_name: str = Field(default="", max_length=255)


class FindingPhotoUploadInput(WriteInput):
    observation_id: int = Field(gt=0)
    file: OpenAIFile


class FindingPhotoInput(FindingIdInput):
    attachment_id: int = Field(gt=0)


class ConnectorFindingResult(MaintenanceObservationItem):
    manager_url: str


class ConnectorDefectActResult(MaintenanceDefectActItem):
    manager_url: str


class ConnectorOfferResult(BaseModel):
    id: int
    source_order_id: int
    continuation_order_id: int
    proposal_id: int
    version: int
    state: str
    manager_url: str


class AvailableMaintenanceProposal(BaseModel):
    proposal_id: int
    name: str
    # Ordinary source prices and line IDs, never guessed amounts or internal cost.
    lines: list[dict]
    lines_complete: bool = True
    pricing: dict


class ConnectorOfferList(MaintenanceOfferList):
    continuation_order_id: int | None
    available_proposals: list[AvailableMaintenanceProposal]
    proposals_have_more: bool = False
    manager_url: str


class ConnectorPhotoResult(ManagerServiceAttachmentItemResponse):
    observation_id: int
    manager_url: str


class ConnectorPhotoReadResult(BaseModel):
    observation_id: int
    attachment_id: int
    mime_type: str
    variant: str
    manager_url: str
