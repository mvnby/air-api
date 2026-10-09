"""Private Drive call material, durable checkpoints and explicit adoption receipts."""

from datetime import datetime

from sqlalchemy import Column, DateTime, JSON, LargeBinary, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from models.tenancy import utc_now


class CallDriveConnection(SQLModel, table=True):
    __tablename__ = "call_drive_connection"
    __table_args__ = (UniqueConstraint("tenant_id", "storefront_id", "staff_user_id", name="uq_call_drive_owner"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False)
    storefront_id: int = Field(foreign_key="storefront.id", nullable=False)
    staff_user_id: int = Field(foreign_key="staff_users.id", nullable=False)
    encrypted_credentials: str | None = Field(default=None, sa_column=Column(Text))
    credentials_fingerprint: str = ""
    account_label: str | None = None
    folder_id: str | None = None
    folder_name: str | None = None
    auto_poll_enabled: bool = False
    page_token: str | None = None
    last_error_code: str | None = None
    last_polled_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class CallRecording(SQLModel, table=True):
    __tablename__ = "call_recording"
    __table_args__ = (UniqueConstraint("connection_id", "file_id", "source_version", name="uq_call_recording_version"),)

    id: int | None = Field(default=None, primary_key=True)
    connection_id: int = Field(foreign_key="call_drive_connection.id", nullable=False, index=True)
    file_id: str
    source_version: str
    source_checksum: str
    source_size: int
    source_url: str
    filename: str
    mime_type: str
    source_modified_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    call_occurred_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    time_source: str = "unknown"
    phone: str | None = None
    # Source registration is explicit; a Drive filename never proves a caller identity.
    origin: str = "drive_selected_folder"
    state: str = Field(default="observing", index=True)
    stage: str = "download"
    observations: int = 1
    observed_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    downloaded_audio: bytes | None = Field(default=None, sa_column=Column(LargeBinary))
    audio_duration_seconds: float | None = None
    transcript: str | None = Field(default=None, sa_column=Column(Text))
    structure: dict | None = Field(default=None, sa_column=Column(JSON))
    stage_attempts: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    last_error_code: str | None = None
    job_event_id: str | None = None
    version: int = 1
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class CallProposal(SQLModel, table=True):
    __tablename__ = "call_proposal"
    __table_args__ = (UniqueConstraint("recording_id", "action_key", name="uq_call_proposal_action"),)

    id: int | None = Field(default=None, primary_key=True)
    recording_id: int = Field(foreign_key="call_recording.id", nullable=False, index=True)
    action_key: str
    kind: str
    payload: dict = Field(sa_column=Column(JSON, nullable=False))
    evidence: str = Field(sa_column=Column(Text, nullable=False))
    needs_clarification: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))


class CallAdoption(SQLModel, table=True):
    __tablename__ = "call_adoption"
    __table_args__ = (UniqueConstraint("connection_id", "file_id", "action_key", name="uq_call_adoption_source_action"),)

    id: int | None = Field(default=None, primary_key=True)
    connection_id: int = Field(foreign_key="call_drive_connection.id", nullable=False)
    file_id: str
    action_key: str
    proposal_id: int = Field(foreign_key="call_proposal.id", nullable=False)
    resource_type: str
    resource_id: int
    payload: dict = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
