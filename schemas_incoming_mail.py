"""Bounded synchronization of the existing private system mailbox."""

from pydantic import BaseModel, ConfigDict, Field


class IncomingMailSyncPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=50, ge=1, le=100)


class IncomingMailSyncResponse(BaseModel):
    processed: int = 0
    captured: int = 0
    skipped: int = 0
    existing: int = 0
    has_more: bool = False
