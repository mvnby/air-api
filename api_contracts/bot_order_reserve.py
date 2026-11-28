"""Order-scoped supplier reservation transport for the staff Mini App."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field


_Id = Annotated[int, Field(gt=0, le=2_147_483_647, strict=True)]


class BotReserveCandidate(BaseModel):
    offer_id: int
    supplier_name: str
    offer_title: str | None
    offer_code: str
    max_quantity: int


class BotReserveRequest(BaseModel):
    id: int
    request_id: int
    supplier_name: str
    quantity: int
    status: str
    intent: Literal["reserve", "order"]
    reserved_until: AwareDatetime | None
    supplier_message: str | None
    can_mark_sent: bool
    can_confirm: bool


class BotReserveLine(BaseModel):
    id: int
    title: str
    quantity: int
    remaining_quantity: int | None
    candidates: list[BotReserveCandidate]
    requests: list[BotReserveRequest]


class BotOrderReserveState(BaseModel):
    enabled: bool
    unavailable_reason: str | None = None
    manager_status: str | None = None
    can_set_order_status: bool = False
    supplier_access: bool = False
    supplier_access_reason: str | None = None
    lines: list[BotReserveLine] = Field(default_factory=list)


class BotSetOrderReserveStatus(BaseModel, extra="forbid"):
    kind: Literal["set_order_reserve_status"]
    status: Literal["pending", "reserved"]


class BotCreateReserveRequest(BaseModel, extra="forbid"):
    kind: Literal["create_reserve_request"]
    line_id: _Id
    offer_id: _Id
    quantity: Annotated[int, Field(gt=0, le=2_147_483_647, strict=True)]


class BotMarkReserveRequestSent(BaseModel, extra="forbid"):
    kind: Literal["mark_reserve_request_sent"]
    line_id: _Id
    request_line_id: _Id


class BotConfirmReserveRequest(BaseModel, extra="forbid"):
    kind: Literal["confirm_reserve_request"]
    line_id: _Id
    request_line_id: _Id
    confirmed: Literal[True]
    reserved_until: AwareDatetime | None = None


BotReserveChange = (
    BotSetOrderReserveStatus | BotCreateReserveRequest | BotMarkReserveRequestSent | BotConfirmReserveRequest
)
