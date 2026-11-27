"""Compact manager CRM projections shared with the autonomous Telegram runtime."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


WorkspaceSection = Literal["incoming", "orders", "customers", "tasks"]
IncomingKind = Literal["lead", "order"]
WorkspaceAction = Literal["mark_read", "mark_unread", "complete", "reopen", "customer_draft", "service_order"]


class BotWorkspaceRow(BaseModel):
    id: int
    kind: Literal["lead", "order", "customer", "task"]
    title: str
    subtitle: str | None = None
    status: str | None = None
    is_read: bool | None = None


class BotWorkspaceList(BaseModel):
    items: list[BotWorkspaceRow]
    total: int
    page: int
    limit: int


class BotWorkspaceFact(BaseModel):
    label: str
    value: str
    kind: Literal["text", "phone", "email"] = "text"


class BotWorkspaceEquipmentLine(BaseModel):
    title: str
    quantity: int
    unit_price: int
    currency: str


class BotWorkspaceProposal(BaseModel):
    name: str
    selected: bool
    equipment: list[BotWorkspaceEquipmentLine]


class BotWorkspaceDetail(BaseModel):
    item: BotWorkspaceRow
    facts: list[BotWorkspaceFact]
    description: str | None = None
    manager_url: HttpUrl
    proposals: list[BotWorkspaceProposal] = Field(default_factory=list)
    actions: list[WorkspaceAction]
    version: int | None = None
    customer_id: int | None = None


class BotWorkspaceActor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    telegram_id: int = Field(gt=0)
    expected_context_version: int = Field(ge=0)


class BotWorkspaceReadRequest(BotWorkspaceActor):
    kind: IncomingKind
    is_read: bool


class BotWorkspaceCommand(BotWorkspaceActor):
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class BotWorkspaceTaskRequest(BotWorkspaceCommand):
    expected_version: int = Field(ge=1)
    action: Literal["complete", "reopen"]


class BotWorkspaceServiceOrderRequest(BotWorkspaceCommand):
    kind: IncomingKind
    customer_id: int = Field(gt=0)
    workflow_type: Literal["repair", "service_work", "maintenance"]


class BotWorkspaceOrderResult(BaseModel):
    order_id: int
