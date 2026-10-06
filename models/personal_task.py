"""Persistent personal tasks shared by Manager and authenticated adapters."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKeyConstraint, Index, Integer, String, Text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PersonalTask(SQLModel, table=True):
    __tablename__ = "personal_task"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_personal_task_status",
        ),
        CheckConstraint("version >= 1", name="ck_personal_task_version_positive"),
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_personal_task_storefront_tenant",
        ),
        Index(
            "ix_personal_task_scope_status_due",
            "tenant_id",
            "storefront_id",
            "status",
            "due_at",
        ),
        Index(
            "ix_personal_task_scope_assignee_status",
            "tenant_id",
            "storefront_id",
            "assignee_staff_user_id",
            "status",
        ),
        Index(
            "ix_personal_task_scope_author_status",
            "tenant_id",
            "storefront_id",
            "author_staff_user_id",
            "status",
        ),
        Index(
            "ix_personal_task_scope_reminder",
            "tenant_id",
            "storefront_id",
            "status",
            "reminder_at",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False)
    storefront_id: int = Field(sa_column=Column(Integer, nullable=False))

    author_staff_user_id: int = Field(
        foreign_key="staff_users.id",
        nullable=False,
        index=True,
    )
    assignee_staff_user_id: Optional[int] = Field(
        default=None,
        foreign_key="staff_users.id",
        index=True,
    )

    text: str = Field(sa_column=Column(String(2000), nullable=False))
    description: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    status: str = Field(
        default="active",
        sa_column=Column(String(16), nullable=False),
    )
    version: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default="1"),
    )

    due_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    reminder_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id", index=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id", index=True)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id", index=True)
    equipment_id: Optional[int] = Field(
        default=None,
        foreign_key="customer_equipment.id",
        index=True,
    )

    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    cancelled_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
