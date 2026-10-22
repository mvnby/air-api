"""Bounded read-side contract for the Manager order queues."""

from pydantic import BaseModel, Field
from schemas_manager_orders import ManagerOrderListItemResponse


class ManagerOrderBoardGroup(BaseModel):
    key: str
    customer_id: int | None = None
    order_id: int | None = None
    customer_name: str
    count: int
    total_amount: float
    balance_due: float
    margin: float | None = None


class ManagerOrderBoardPage(BaseModel):
    items: list[ManagerOrderListItemResponse] = Field(default_factory=list)
    groups: list[ManagerOrderBoardGroup] = Field(default_factory=list)
    total: int
    total_orders: int
    page: int
    limit: int
    has_more: bool
    queue_counts: dict[str, int]
    work_counts: dict[str, int]
