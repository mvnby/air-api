"""Private mailbox history, independent of CRM intake and orders."""

from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON, LargeBinary, UniqueConstraint, String, BigInteger, text
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
    reply_to: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False, server_default=text("'[]'")))
    in_reply_to: str | None = None
    references: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False, server_default=text("'[]'")))
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


class MailSyncCursor(SQLModel, table=True):
    __tablename__ = "mail_sync_cursor"
    __table_args__ = (UniqueConstraint("tenant_id", "account_id", "folder", name="uq_mail_sync_cursor_scope"),)

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id")
    account_id: str = Field(default="system", sa_column=Column(String(64), nullable=False))
    folder: str = Field(sa_column=Column(String(512), nullable=False))
    uidvalidity: str = Field(sa_column=Column(String(64), nullable=False))
    last_uid: int = Field(default=0, sa_column=Column(BigInteger, nullable=False))
    # None means bootstrap; zero means history exhausted. Otherwise exclusive upper bound.
    history_before_uid: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
