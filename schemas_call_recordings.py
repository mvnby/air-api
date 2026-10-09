"""Calls are private review material; adoption never schedules confirmed work."""

from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from schemas_incoming import IncomingFields
from schemas_personal_tasks import PersonalTaskCreatePayload


class CallDriveStatus(BaseModel):
    connected: bool
    pipeline_enabled: bool
    transcription_configured: bool
    account_label: str | None = None
    folder_id: str | None = None
    folder_name: str | None = None
    folder_url: str | None = None
    auto_poll_enabled: bool = False
    last_error_code: str | None = None
    max_bytes: int = 10 * 1024 * 1024
    max_duration_seconds: int = 600
    max_files_per_poll: int = 5
    max_recordings_per_day: int = 20
    max_stage_attempts: int = 3
    transcription_model: str
    structure_model: str


class CallFolderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    folder_id: str = Field(pattern=r"^[A-Za-z0-9_-]{10,160}$")
    auto_poll_enabled: bool = False


class CallPollPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{10,160}$")


class CallPollResponse(BaseModel):
    observed: int
    queued: int
    has_more: bool


class CallRecordingMetadataPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    call_occurred_at: AwareDatetime | None = None
    phone: str | None = None


class CallRetryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class CallAdoptPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    incoming: IncomingFields | None = None
    task: PersonalTaskCreatePayload | None = None


class CallProposalResponse(BaseModel):
    id: int
    kind: Literal["incoming", "task", "callback"]
    payload: dict
    evidence: str
    needs_clarification: list[str]
    requested_date: date | None = Field(default=None, description="Desired Minsk day derived from the original call clock; does not imply an hour or confirmed visit.")
    date_precision: Literal["date", "datetime"] | None = Field(default=None, description="Same desired-date precision as IncomingResponse. Date-only proposals leave payload.requested_at empty; an explicit manual timestamp has datetime precision.")
    accepted_resource_type: str | None = None
    accepted_resource_id: int | None = None
    accepted_url: str | None = None


class CallRecordingResponse(BaseModel):
    id: int
    version: int
    file_id: str
    source_version: str
    source_checksum: str
    source_size: int
    source_url: str
    filename: str
    mime_type: str
    origin: str
    call_occurred_at: datetime | None
    time_source: str
    phone: str | None
    state: str
    stage: str
    stage_attempts: dict
    last_error_code: str | None
    transcript: str | None = None
    structure: dict | None = None
    audio_duration_seconds: float | None
    proposals: list[CallProposalResponse] = Field(default_factory=list)


class CallRecordingListResponse(BaseModel):
    items: list[CallRecordingResponse]
    total: int


class CallAdoptionResponse(BaseModel):
    resource_type: str
    resource_id: int
    resource_url: str
    replayed: bool = False
