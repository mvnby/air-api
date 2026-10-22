"""Explicit, optimistic wait/resume command; the contact date is optional."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class ManagerOrderWaitingCommand(BaseModel):
    action: Literal["wait", "resume"]
    expected_revision: int = Field(ge=0)
    reason_code: (
        Literal["next_stage", "site_readiness", "customer_decision", "other"] | None
    ) = None
    note: str | None = Field(default=None, max_length=2000)
    next_followup_date: datetime | None = None
