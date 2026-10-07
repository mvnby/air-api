"""Persistent continuation and immutable observation-version document sources."""
from datetime import datetime

from sqlalchemy import Column, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from models.maintenance_observation import utc_now


class MaintenanceContinuation(SQLModel, table=True):
    __tablename__ = "maintenance_continuation"
    id: int | None = Field(default=None, primary_key=True)
    source_order_id: int = Field(foreign_key="order.id", unique=True)
    order_id: int = Field(foreign_key="order.id", unique=True)
    tenant_id: int = Field(foreign_key="tenant.id")
    storefront_id: int = Field(foreign_key="storefront.id")
    customer_id: int = Field(foreign_key="customer.id", index=True)
    customer_branch_id: int | None = Field(default=None, foreign_key="customer_branches.id", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str = Field(sa_column=Column(String(160), nullable=False))


class MaintenanceActPreparation(SQLModel, table=True):
    __tablename__ = "maintenance_act_preparation"
    __table_args__ = (UniqueConstraint("continuation_id", "command_key", name="uq_maintenance_act_command"),)
    id: int | None = Field(default=None, primary_key=True)
    continuation_id: int = Field(foreign_key="maintenance_continuation.id", index=True)
    document_id: int | None = Field(default=None, foreign_key="order_document.id", unique=True)
    command_key: str = Field(sa_column=Column(String(36), nullable=False))
    command_hash: str = Field(sa_column=Column(String(64), nullable=False))
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str = Field(sa_column=Column(String(160), nullable=False))


class MaintenanceActSource(SQLModel, table=True):
    __tablename__ = "maintenance_act_source"
    __table_args__ = (UniqueConstraint("preparation_id", "revision_id", name="uq_maintenance_act_source"),)
    id: int | None = Field(default=None, primary_key=True)
    preparation_id: int = Field(foreign_key="maintenance_act_preparation.id", index=True)
    revision_id: int = Field(foreign_key="maintenance_observation_revision.id", index=True)
