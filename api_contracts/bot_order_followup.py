"""Order follow-up operations exposed to staff Telegram clients."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


ScheduleField = Literal["measurement_date", "installation_date", "next_followup_date"]
WaitingReason = Literal["next_stage", "site_readiness", "customer_decision", "other"]
CustomerParty = Literal["individual", "individual_entrepreneur", "company"]
WorkflowAction = Literal[
    "negotiation:awaiting_offer", "negotiation:awaiting_visit", "negotiation:proposal_sent",
    "negotiation:awaiting_signature", "negotiation:awaiting_payment", "negotiation:follow_up",
    "execution:order_equipment", "execution:awaiting_equipment", "execution:needs_schedule",
    "execution:scheduled", "execution:work_done", "execution:awaiting_documents",
    "execution:awaiting_payment", "closed_won", "closed_lost", "wait", "resume",
]


class BotOrderFollowupCustomer(BaseModel):
    id: int
    name: str
    type: CustomerParty
    phone: str | None = None
    email: str | None = None


class BotOrderWorkflowAction(BaseModel):
    action: WorkflowAction
    label: str
    requires_confirmation: bool = False
    requires_reason: bool = False
    requires_reason_code: bool = False


class BotOrderFollowup(BaseModel):
    status: Literal["new_lead", "negotiation", "execution", "closed"]
    closing_result: Literal["won", "lost"] | None = None
    reject_reason: str | None = None
    customer: BotOrderFollowupCustomer | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    delivery_address: str | None = None
    comment: str | None = None
    measurement_required: bool = False
    measurement_date: datetime | None = None
    installation_date: datetime | None = None
    next_followup_date: datetime | None = None
    negotiation_status: str | None = None
    execution_status: str | None = None
    workflow_status_label: str | None = None
    is_on_hold: bool = False
    on_hold_reason_code: str | None = None
    on_hold_reason: str | None = None
    can_edit_details: bool = False
    can_assign_customer: bool = False
    can_create_customer: bool = False
    customer_assignment_requires_confirmation: bool = False
    schedule_fields: list[ScheduleField] = Field(default_factory=list)
    workflow_actions: list[BotOrderWorkflowAction] = Field(default_factory=list)


class _BotOrderFollowupChange(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BotOrderSetDetails(_BotOrderFollowupChange):
    kind: Literal["set_details"]
    contact_name: str | None = Field(default=None, min_length=1, max_length=250)
    contact_phone: str | None = Field(default=None, min_length=1, max_length=100)
    delivery_address: str | None = Field(default=None, min_length=1, max_length=1000)
    comment: str | None = Field(default=None, min_length=1, max_length=8000)

    @model_validator(mode="after")
    def require_field(self):
        if self.model_fields_set == {"kind"}:
            raise ValueError("Укажите поля заказа для изменения")
        return self


class BotOrderAssignCustomer(_BotOrderFollowupChange):
    kind: Literal["assign_customer"]
    customer_id: int = Field(gt=0, strict=True)
    confirmed: bool = Field(default=False, strict=True)


class BotOrderCreateCustomer(_BotOrderFollowupChange):
    kind: Literal["create_customer"]
    name: str = Field(min_length=1, max_length=250)
    customer_type: CustomerParty
    phone: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=1, max_length=254)
    inn: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def require_identity(self):
        if not (self.phone or self.email or self.inn):
            raise ValueError("Для создания клиента укажите телефон, email или УНП")
        return self


class BotOrderSetSchedule(_BotOrderFollowupChange):
    kind: Literal["set_schedule"]
    field: ScheduleField
    date: datetime | None

    @field_validator("date", mode="before")
    @classmethod
    def require_datetime(cls, value):
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str) and len(value) > 10 and value[10] in "Tt ":
            return value
        raise ValueError("Укажите дату и время по Минску")


class BotOrderTransition(_BotOrderFollowupChange):
    kind: Literal["transition_order"]
    action: WorkflowAction
    confirmed: bool = Field(default=False, strict=True)
    reason: Annotated[str, StringConstraints(min_length=1, max_length=2000)] | None = None
    reason_code: WaitingReason | None = None


BotOrderFollowupChange = Annotated[
    BotOrderSetDetails | BotOrderAssignCustomer | BotOrderCreateCustomer | BotOrderSetSchedule | BotOrderTransition,
    Field(discriminator="kind"),
]
