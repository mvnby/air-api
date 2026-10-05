from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class JevShadowItem(BaseModel):
    id: int
    source: Literal["email", "belzakupki"]
    subject: str
    state: str
    created_at: datetime
    status: Literal["queued", "running", "completed", "failed"]
    primary_provider: str
    primary_model_requested: str | None
    primary_is_relevant: bool | None
    primary_duration_ms: int | None
    model: str | None
    kind: str | None
    kind_confidence: float | None
    hvac_probability: float | None
    jev_is_relevant: bool | None
    duration_ms: int | None
    input_tokens: int | None
    estimated_usd: float | None
    error_code: str | None


class JevShadowReport(BaseModel):
    queued: int
    running: int
    completed: int
    failed: int
    comparable: int
    agreements: int
    disagreements: int
    estimated_usd: float
    input_tokens: int
    median_duration_ms: float | None
    items: list[JevShadowItem]
