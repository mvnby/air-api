"""Private durable bytes for the existing outgoing message journal."""

from typing import Any

from sqlalchemy import Column, JSON, LargeBinary
from sqlmodel import Field, SQLModel


class MailAttachmentSnapshot(SQLModel, table=True):
    __tablename__ = "mail_attachment_snapshot"

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    email_id: int = Field(foreign_key="outgoing_email.id", index=True)
    filename: str
    mime_type: str = "application/octet-stream"
    size: int
    sha256: str
    source_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    content: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
