"""Shared Manager and connector contract for scoped equipment inspections."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from schemas_connector_mcp import ConnectorInput, WriteInput


OrderInspectionStatus = Literal["defect_found", "no_defect_found", "inconclusive", "restored"]
OrderTechnicalActType = Literal["technical_inspection_act", "defect_act"]
InspectionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class OrderInspectionFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: OrderInspectionStatus
    facts: InspectionText
    trial_result: InspectionText | None = None
    event_history: InspectionText | None = None
    recommendations: InspectionText | None = None
    performed_actions: InspectionText | None = None
    inspected_at: AwareDatetime | None = None
    performer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)] | None = None

    @model_validator(mode="after")
    def require_restoration_evidence(self):
        if self.status == "restored" and not self.performed_actions:
            raise ValueError("Укажите выполненные действия, после которых работа восстановилась")
        return self


class OrderInspectionTarget(ConnectorInput):
    order_id: int = Field(gt=0)
    site_id: int = Field(gt=0)
    equipment_id: int = Field(gt=0)


class OrderInspectionReadInput(OrderInspectionTarget):
    version: int | None = Field(default=None, gt=0)


class OrderInspectionSavePayload(OrderInspectionFacts, WriteInput):
    expected_version: int = Field(ge=0)


class OrderInspectionSaveInput(OrderInspectionSavePayload, OrderInspectionTarget):
    pass


class OrderInspectionRevisionItem(OrderInspectionFacts):
    revision_id: int
    version: int
    recorded_at: datetime
    recorded_by: str


class OrderInspectionState(OrderInspectionTarget):
    current_version: int
    inspection: OrderInspectionRevisionItem | None = None


class OrderInspectionSaved(OrderInspectionTarget):
    revision_id: int
    version: int


class TechnicalActInspection(ConnectorInput):
    equipment_id: int = Field(gt=0)
    expected_version: int = Field(gt=0)


class PrepareOrderTechnicalActPayload(WriteInput):
    expected_site_version: int = Field(gt=0)
    document_type: OrderTechnicalActType
    inspections: list[TechnicalActInspection] = Field(min_length=1, max_length=100)
    legal_entity_id: int = Field(gt=0)
    issue_date: date
    base_document_id: int | None = Field(default=None, gt=0)
    base_customer_contract_id: int | None = Field(default=None, gt=0)
    template_id: int | None = Field(default=None, gt=0)
    replaces_document_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_scope(self):
        if (self.base_document_id is None) == (self.base_customer_contract_id is None):
            raise ValueError("Выберите одно основание для технического акта")
        if len({item.equipment_id for item in self.inspections}) != len(self.inspections):
            raise ValueError("Укажите каждую единицу оборудования один раз")
        return self


class PrepareOrderTechnicalActInput(PrepareOrderTechnicalActPayload):
    order_id: int = Field(gt=0)
    site_id: int = Field(gt=0)


class OrderTechnicalActPrepared(BaseModel):
    order_id: int
    site_id: int
    equipment_ids: list[int]
    document_id: int
    document_type: OrderTechnicalActType
    status: str
    revision: str
    manager_url: str
