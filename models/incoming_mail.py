"""Private mailbox history, independent of CRM intake and orders."""

from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON, LargeBinary, UniqueConstraint
from sqlmodel import Field, SQLModel


class IncomingMail(SQLModel, table=True):
    __tablename__ = "incoming_mail"
    __table_args__ = (
        UniqueConstraint("tenant_id", "account_id", "source_key", name="uq_incoming_mail_source"),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    account_id: str = Field(default="system")
    source_key: str = Field(index=True)
    message_id: str | None = None
    sender_email: str = ""
    sender_name: str = ""
    recipient_email: str = ""
    cc_emails: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    subject: str = ""
    body_text: str = ""
    body_html: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    order_id: int | None = Field(default=None, foreign_key="order.id", index=True)
    customer_id: int | None = Field(default=None, foreign_key="customer.id", index=True)
    received_at: datetime = Field(default_factory=datetime.now, index=True)
    created_at: datetime = Field(default_factory=datetime.now)


class IncomingMailAttachment(SQLModel, table=True):
    __tablename__ = "incoming_mail_attachment"

    id: int | None = Field(default=None, primary_key=True)
    email_id: int = Field(foreign_key="incoming_mail.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    filename: str
    mime_type: str
    size: int
    sha256: str
    content: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
