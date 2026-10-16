"""Explicit installer read projections and Manager-controlled work publication."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from services.service_estimate_money import exact_money


class WorkerPerson(BaseModel):
    staff_user_id: int
    display_name: str
    avatar_url: str | None = None


class WorkerCandidatesResponse(BaseModel):
    items: list[WorkerPerson]
    total: int
    page: int
    limit: int


class WorkerAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staff_user_id: int = Field(gt=0)
    work_stage_id: int | None = Field(default=None, gt=0)


class WorkerAssignmentRevoke(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)


class WorkerAssignmentPublicationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=160)
    instructions: str = Field(default="", max_length=8000)
    material_link_ids: list[int] = Field(default_factory=list, max_length=30)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Укажите название работы")
        return value.strip()

    @field_validator("material_link_ids")
    @classmethod
    def unique_positive_links(cls, value):
        if any(item <= 0 for item in value) or len(value) != len(set(value)):
            raise ValueError(
                "Материалы должны иметь разные положительные идентификаторы"
            )
        return value


class InstallerCollection(BaseModel):
    status: Literal["not_assigned", "not_collector", "ready", "requires_review"]
    amount: str | None = None
    currency: Literal["BYN", "USD", "EUR"] | None = None
    recipient_name: str | None = None
    updated_at: datetime | None = None


class InstallerWorkSummary(BaseModel):
    id: int
    order_id: int
    work_stage_id: int | None
    version: int
    title: str
    status: str
    start_time: datetime | None
    end_time: datetime | None = None
    customer_name: str
    customer_phone: str | None = None
    address: str | None = None
    collection: InstallerCollection


class InstallerWorksResponse(BaseModel):
    items: list[InstallerWorkSummary]
    total: int
    page: int
    limit: int


class InstallerTechnicalSpec(BaseModel):
    label: str
    value: str


class InstallerEquipment(BaseModel):
    key: str
    name: str
    brand: str | None = None
    model: str | None = None
    serial: str | None = None
    quantity: int = Field(ge=1)
    technical_specs: list[InstallerTechnicalSpec] = Field(default_factory=list)


class InstallerMaterial(BaseModel):
    id: int
    label: str
    file_kind: Literal["image", "pdf"]
    content_url: str


class InstallerWorkDetail(InstallerWorkSummary):
    instructions: str
    equipment: list[InstallerEquipment]
    materials: list[InstallerMaterial]


class ManagerWorkerAssignment(BaseModel):
    id: int
    staff_user_id: int
    display_name: str
    work_stage_id: int | None
    version: int
    title: str
    instructions: str
    source: str
    revoked_at: datetime | None
    is_active: bool
    material_link_ids: list[int]


class ManagerWorkerMaterial(BaseModel):
    link_id: int
    label: str
    file_kind: Literal["image", "pdf"]
    work_stage_id: int | None


class ManagerCollectionBalance(BaseModel):
    currency: Literal["BYN", "USD", "EUR"]
    remaining_amount: str


class ManagerCollectionInstruction(BaseModel):
    version: int
    assignment_id: int | None
    amount: str | None
    currency: Literal["BYN", "USD", "EUR"] | None
    status: Literal["not_assigned", "ready", "requires_review"]
    updated_at: datetime | None


class ManagerInstallerWorkspace(BaseModel):
    order_id: int
    assignments: list[ManagerWorkerAssignment]
    materials: list[ManagerWorkerMaterial]
    collection: ManagerCollectionInstruction
    balances: list[ManagerCollectionBalance]
    financial_fingerprint: str


class ManagerCollectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    assignment_id: int | None = Field(gt=0)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: Literal["BYN", "USD", "EUR"] | None = None
    financial_fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("amount")
    @classmethod
    def exact_amount(cls, value):
        return exact_money(value) if value is not None else None

    @model_validator(mode="after")
    def complete_instruction(self):
        if self.assignment_id is None:
            if self.amount is not None or self.currency is not None:
                raise ValueError("При отмене поручения сумма и валюта не указываются")
        elif self.amount is None or self.currency is None:
            raise ValueError("Укажите сумму и валюту поручения")
        return self
