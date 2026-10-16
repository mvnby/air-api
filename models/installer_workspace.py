"""Explicit company worker eligibility and work access, separate from payroll."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel


def utc_now():
    return datetime.now(timezone.utc)


class TenantWorkerProfile(SQLModel, table=True):
    __tablename__ = "tenant_worker_profile"
    __table_args__ = (
        UniqueConstraint("tenant_id", "staff_user_id", name="uq_worker_profile_tenant_staff"),
        UniqueConstraint("id", "tenant_id", name="uq_worker_profile_id_tenant"),
        ForeignKeyConstraint(["tenant_id", "staff_user_id"], ["tenant_membership.tenant_id", "tenant_membership.staff_user_id"], name="fk_worker_profile_membership", ondelete="RESTRICT"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_worker_profile_status"),
        CheckConstraint("version >= 0", name="ck_worker_profile_version"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    staff_user_id: int = Field(foreign_key="staff_users.id", index=True)
    status: str = Field(default="active", sa_column=Column(String(16), nullable=False, server_default="active"))
    canonical_legacy_installer_id: Optional[int] = Field(default=None, foreign_key="installers.id")
    version: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))


class OrderWorkAssignment(SQLModel, table=True):
    __tablename__ = "order_work_assignment"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", "storefront_id", "order_id", name="uq_work_assignment_id_scope"),
        ForeignKeyConstraint(["order_id", "tenant_id", "storefront_id"], ["order.id", "order.tenant_id", "order.storefront_id"], name="fk_work_assignment_order_scope", ondelete="CASCADE"),
        ForeignKeyConstraint(["work_stage_id", "order_id"], ["order_work_stage.id", "order_work_stage.order_id"], name="fk_work_assignment_stage_order", ondelete="CASCADE"),
        ForeignKeyConstraint(["worker_profile_id", "tenant_id"], ["tenant_worker_profile.id", "tenant_worker_profile.tenant_id"], name="fk_work_assignment_profile_tenant", ondelete="RESTRICT"),
        CheckConstraint("version >= 0", name="ck_work_assignment_version"),
        CheckConstraint("source IN ('manual', 'legacy_order', 'legacy_stage')", name="ck_work_assignment_source"),
        Index("uq_work_assignment_active_order", "tenant_id", "order_id", "worker_profile_id", unique=True,
              postgresql_where=text("revoked_at IS NULL AND work_stage_id IS NULL"), sqlite_where=text("revoked_at IS NULL AND work_stage_id IS NULL")),
        Index("uq_work_assignment_active_stage", "tenant_id", "order_id", "work_stage_id", "worker_profile_id", unique=True,
              postgresql_where=text("revoked_at IS NULL AND work_stage_id IS NOT NULL"), sqlite_where=text("revoked_at IS NULL AND work_stage_id IS NOT NULL")),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(index=True)
    storefront_id: int = Field(index=True)
    order_id: int = Field(index=True)
    work_stage_id: Optional[int] = Field(default=None, index=True)
    worker_profile_id: int = Field(index=True)
    version: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    revoked_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    instructions: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    title: str = Field(default="Монтаж", sa_column=Column(String(160), nullable=False, server_default="Монтаж"))
    source: str = Field(default="manual", sa_column=Column(String(20), nullable=False, server_default="manual"))
