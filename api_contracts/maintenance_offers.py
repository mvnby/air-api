"""Explicit maintenance commercial commands. Money comes from ordinary order lines."""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from api_contracts.maintenance_observations import MaintenanceActSelectedObservation


class MaintenanceOfferLine(MaintenanceActSelectedObservation):
    kind: Literal['service', 'product']
    line_id: int = Field(gt=0)
    purpose: Literal['diagnosis', 'repair']


class PrepareMaintenanceOffer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    command_key: UUID
    proposal_id: int = Field(gt=0)
    lines: list[MaintenanceOfferLine] = Field(min_length=1, max_length=100)

    @field_validator('lines')
    @classmethod
    def unique_lines(cls, values):
        if len({(x.kind, x.line_id) for x in values}) != len(values):
            raise ValueError('Каждая строка должна относиться к одному замечанию')
        return sorted(values, key=lambda x: (x.kind, x.line_id))


class MaintenanceOfferCommand(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    command_key: UUID
    expected_version: int = Field(ge=0)
    action: Literal['issue', 'send', 'accept', 'reject', 'defer', 'continue']
    source: str = Field(min_length=1, max_length=1000)
    comment: str = Field(min_length=1, max_length=10000)
    occurred_at: datetime
    accepted_lines: list[str] = Field(default_factory=list, max_length=100)

    @field_validator('occurred_at')
    @classmethod
    def time(cls, value):
        if value.tzinfo is None:
            raise ValueError('Укажите часовой пояс')
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @model_validator(mode='after')
    def selection(self):
        if bool(self.accepted_lines) != (self.action == 'accept'):
            raise ValueError('Согласие требует выбранные строки; другие команды не принимают состав')
        if len(set(self.accepted_lines)) != len(self.accepted_lines):
            raise ValueError('Строки согласия повторяются')
        self.accepted_lines.sort()
        return self


class ResolveMaintenanceObservation(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    command_key: UUID
    expected_version: int = Field(ge=1)
    offer_id: int = Field(gt=0)
    evidence: str = Field(min_length=1, max_length=10000)
    resolved_at: datetime

    @field_validator('resolved_at')
    @classmethod
    def time(cls, value):
        return MaintenanceOfferCommand.time(value)


class MaintenanceOfferItem(BaseModel):
    id: int
    source_order_id: int
    continuation_order_id: int
    proposal_id: int
    version: int
    state: str
    snapshot: dict
    events: list[dict]
    resolutions: list[dict]


class MaintenanceOfferList(BaseModel):
    items: list[MaintenanceOfferItem]
    total: int


class MaintenanceWorkspaceItem(BaseModel):
    source_order_id: int
    continuation_order_id: int
