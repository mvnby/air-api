"""Finite, content-free vocabulary for order-workspace usage counters."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OrderUsageWorkflow = Literal["sales_installation", "work", "maintenance", "repair"]
OrderUsageParty = Literal["individual", "individual_entrepreneur", "company", "unknown"]
OrderUsageViewport = Literal["mobile", "tablet", "desktop"]
OrderUsageMetric = Literal[
    "order_open", "proposal_open", "documents_open", "work_open", "payments_open",
    "customer_open", "object_edit", "equipment_open", "attachments_open",
    "product_add", "product_select", "product_description_edit", "product_remove",
    "service_add", "service_edit", "service_remove", "scenario_change",
    "autosave_toggle", "document_create", "payment_add",
]


class OrderUsageEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: OrderUsageMetric
    workflow: OrderUsageWorkflow
    party_kind: OrderUsageParty
    viewport: OrderUsageViewport


class OrderUsageBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout_version: Literal["workspace_v1"] = "workspace_v1"
    events: list[OrderUsageEvent] = Field(min_length=1, max_length=25)


class OrderUsageAccepted(BaseModel):
    accepted: int


class OrderUsageDailyItem(OrderUsageEvent):
    day: date
    count: int


class OrderUsageReport(BaseModel):
    days: int
    since: date
    through: date
    timezone: Literal["Europe/Minsk"] = "Europe/Minsk"
    layout_version: Literal["workspace_v1"] = "workspace_v1"
    items: list[OrderUsageDailyItem]
