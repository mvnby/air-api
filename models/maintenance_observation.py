"""Standalone maintenance findings, independent of executed service events."""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import CheckConstraint, Column, JSON, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MaintenanceObservation(SQLModel, table=True):
    __tablename__ = "maintenance_observation"
    __table_args__ = (
        UniqueConstraint("source_order_id", "command_key", name="uq_maintenance_observation_command"),
        CheckConstraint("version >= 1", name="ck_maintenance_observation_version"),
    )
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    storefront_id: int = Field(foreign_key="storefront.id", index=True)
    source_order_id: int = Field(foreign_key="order.id", index=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)
    customer_branch_id: int | None = Field(default=None, foreign_key="customer_branches.id", index=True)
    equipment_id: int | None = Field(default=None, foreign_key="customer_equipment.id", index=True)
    command_key: str = Field(sa_column=Column(String(36), nullable=False))
    command_hash: str = Field(sa_column=Column(String(64), nullable=False))
    origin: str = Field(default="manager_maintenance", sa_column=Column(String(64), nullable=False))
    observed_at: datetime
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str = Field(sa_column=Column(String(160), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now)
    updated_by: str = Field(sa_column=Column(String(160), nullable=False))
    version: int = Field(default=1)
    original_comment: str = Field(sa_column=Column(Text, nullable=False))
    equipment_description: str = Field(sa_column=Column(Text, nullable=False))
    facts: str = Field(sa_column=Column(Text, nullable=False))
    recommendation: str = Field(sa_column=Column(Text, nullable=False))


class MaintenanceObservationRevision(SQLModel, table=True):
    __tablename__ = "maintenance_observation_revision"
    __table_args__ = (
        UniqueConstraint("observation_id", "version", name="uq_maintenance_observation_revision"),
    )
    id: int | None = Field(default=None, primary_key=True)
    observation_id: int = Field(foreign_key="maintenance_observation.id", index=True)
    version: int
    actor: str = Field(sa_column=Column(String(160), nullable=False))
    created_at: datetime = Field(default_factory=utc_now)
    snapshot: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))


class MaintenanceObservationPhoto(SQLModel, table=True):
    __tablename__ = "maintenance_observation_photo"
    __table_args__ = (
        UniqueConstraint("observation_id", "command_key", name="uq_maintenance_observation_photo_command"),
        UniqueConstraint("attachment_id", name="uq_maintenance_observation_photo_attachment"),
    )
    id: int | None = Field(default=None, primary_key=True)
    observation_id: int = Field(foreign_key="maintenance_observation.id", index=True)
    attachment_id: int = Field(foreign_key="service_attachment.id", index=True)
    command_key: str = Field(sa_column=Column(String(36), nullable=False))
    command_hash: str = Field(sa_column=Column(String(64), nullable=False))
