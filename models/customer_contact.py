from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, text
from sqlmodel import Field, SQLModel


class CustomerContact(SQLModel, table=True):
    __tablename__ = "customer_contact"
    __table_args__ = (
        Index(
            "uq_customer_contact_primary",
            "customer_id",
            unique=True,
            postgresql_where=text("is_primary"),
            sqlite_where=text("is_primary = 1"),
        ),
        Index("ix_customer_contact_customer_active", "customer_id", "is_active"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("customer.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    name: Optional[str] = Field(default=None, sa_column=Column(String(200), nullable=True))
    role: Optional[str] = Field(default=None, sa_column=Column(String(120), nullable=True))
    phone: Optional[str] = Field(default=None, sa_column=Column(String(80), nullable=True))
    email: Optional[str] = Field(default=None, sa_column=Column(String(254), nullable=True))
    is_primary: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false")))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, server_default=text("true")))
    is_legacy: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false")))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))


class CustomerContactHistory(SQLModel, table=True):
    __tablename__ = "customer_contact_history"
    __table_args__ = (
        Index("ix_customer_contact_history_customer_changed", "customer_id", "changed_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("customer.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    contact_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("customer_contact.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    field_name: str = Field(sa_column=Column(String(40), nullable=False))
    old_value: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    new_value: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    author_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("staff_users.id", ondelete="SET NULL"), nullable=True),
    )
    author_name: Optional[str] = Field(default=None, sa_column=Column(String(160), nullable=True))
    changed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
