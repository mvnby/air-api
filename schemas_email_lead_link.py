"""Manager contracts for resolving an email lead into an existing order."""

from pydantic import BaseModel, Field


class EmailLeadLinkPayload(BaseModel):
    target_order_id: int = Field(gt=0)


class EmailLeadLinkTarget(BaseModel):
    order_id: int
    title: str
    customer_name: str
    status: str


class EmailLeadLinkResult(BaseModel):
    source_order_id: int
    target_order_id: int
    linked_files: int


class EmailLeadUnlinkResult(BaseModel):
    source_order_id: int
    previous_target_order_id: int
