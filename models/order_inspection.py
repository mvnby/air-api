"""Immutable revisions of an inspection keyed by its scoped equipment link."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKeyConstraint, String, UniqueConstraint
from sqlmodel import Field, SQLModel


class OrderInspectionRevision(SQLModel, table=True):
    __tablename__ = "order_inspection_revision"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "site_id", "equipment_id"],
            ["order_site_equipment.order_id", "order_site_equipment.site_id", "order_site_equipment.equipment_id"],
            name="fk_order_inspection_revision_site_equipment",
            ondelete="CASCADE",
        ),
        UniqueConstraint("order_id", "site_id", "equipment_id", "version", name="uq_order_inspection_revision_version"),
        CheckConstraint("version >= 1", name="ck_order_inspection_revision_version"),
    )

    id: int | None = Field(default=None, primary_key=True)
    order_id: int
    site_id: int
    equipment_id: int
    version: int
    recorded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    actor_staff_user_id: int = Field(foreign_key="staff_users.id")
    recorded_by: str = Field(sa_column=Column(String(160), nullable=False))
    facts: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
