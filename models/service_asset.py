from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, Column, JSON, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class ServiceAttachment(SQLModel, table=True):
    """Private source file used as evidence in service and warranty workflows."""

    __tablename__ = "service_attachment"

    id: Optional[int] = Field(default=None, primary_key=True)
    file_kind: str = Field(default="other", sa_column=Column(String(32), nullable=False, index=True))
    original_filename: str = Field(sa_column=Column(String(255), nullable=False))
    mime_type: str = Field(default="application/octet-stream", sa_column=Column(String(160), nullable=False))
    size_bytes: int = Field(default=0)
    content_hash: Optional[str] = Field(
        default=None,
        sa_column=Column(String(64), nullable=True, index=True),
    )

    storage_provider: str = Field(default="local", sa_column=Column(String(32), nullable=False, index=True))
    storage_key: Optional[str] = Field(default=None, sa_column=Column(String(1024), nullable=True))
    preview_storage_key: Optional[str] = Field(default=None, sa_column=Column(String(1024), nullable=True))
    preview_mime_type: Optional[str] = Field(default=None, sa_column=Column(String(160), nullable=True))

    source: str = Field(default="manager", sa_column=Column(String(64), nullable=False, index=True))
    processing_status: str = Field(default="ready", sa_column=Column(String(32), nullable=False, index=True))
    processing_error: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    transcript: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    source_meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    telegram_file_id: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True, index=True))
    telegram_chat_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True, index=True))
    telegram_message_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True, index=True))
    telegram_user_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True, index=True))

    captured_at: Optional[datetime] = Field(default=None, index=True)
    created_by: Optional[str] = Field(default=None, sa_column=Column(String(160), nullable=True, index=True))
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})
    archived_at: Optional[datetime] = Field(default=None, index=True)


class OrderAttachmentLink(SQLModel, table=True):
    __tablename__ = "order_attachment_link"
    __table_args__ = (
        UniqueConstraint("order_id", "attachment_id", name="uq_order_attachment_link"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", index=True)
    attachment_id: int = Field(foreign_key="service_attachment.id", index=True)
    work_stage_id: Optional[int] = Field(default=None, foreign_key="order_work_stage.id", index=True)
    category: str = Field(default="other", sa_column=Column(String(64), nullable=False, index=True))
    caption: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    archived_at: Optional[datetime] = Field(default=None, index=True)


class EquipmentAttachmentLink(SQLModel, table=True):
    __tablename__ = "equipment_attachment_link"
    __table_args__ = (
        UniqueConstraint("equipment_id", "attachment_id", name="uq_equipment_attachment_link"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    equipment_id: int = Field(foreign_key="customer_equipment.id", index=True)
    attachment_id: int = Field(foreign_key="service_attachment.id", index=True)
    order_attachment_link_id: Optional[int] = Field(
        default=None,
        foreign_key="order_attachment_link.id",
        index=True,
    )
    component_id: Optional[int] = Field(default=None, foreign_key="equipment_component.id", index=True)
    service_history_id: Optional[int] = Field(default=None, foreign_key="equipment_service_history.id", index=True)
    category: str = Field(default="other", sa_column=Column(String(64), nullable=False, index=True))
    caption: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    archived_at: Optional[datetime] = Field(default=None, index=True)


class EquipmentOrderLink(SQLModel, table=True):
    __tablename__ = "equipment_order_link"
    __table_args__ = (
        UniqueConstraint("equipment_id", "order_id", "role", name="uq_equipment_order_link_role"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    equipment_id: int = Field(foreign_key="customer_equipment.id", index=True)
    order_id: int = Field(foreign_key="order.id", index=True)
    role: str = Field(default="other", sa_column=Column(String(32), nullable=False, index=True))
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class WarrantyPolicy(SQLModel, table=True):
    __tablename__ = "warranty_policy"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    coverage_type: str = Field(default="supplier", sa_column=Column(String(32), nullable=False, index=True))
    supplier_id: Optional[int] = Field(default=None, foreign_key="supplier.id", index=True)
    brand_id: Optional[int] = Field(default=None, foreign_key="brand.id", index=True)
    series_id: Optional[int] = Field(default=None, foreign_key="product_series.id", index=True)
    product_id: Optional[int] = Field(default=None, foreign_key="product.id", index=True)

    duration_months: Optional[int] = Field(default=None)
    start_event: str = Field(default="commissioning", sa_column=Column(String(32), nullable=False))
    maintenance_required: bool = Field(default=False, index=True)
    maintenance_interval_months: Optional[int] = Field(default=None)
    grace_period_days: int = Field(default=0)
    allowed_maintenance_provider: str = Field(default="any", sa_column=Column(String(32), nullable=False))
    terms: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    effective_from: Optional[datetime] = Field(default=None, index=True)
    effective_until: Optional[datetime] = Field(default=None, index=True)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})


class EquipmentWarrantyCoverage(SQLModel, table=True):
    __tablename__ = "equipment_warranty_coverage"
    __table_args__ = (
        UniqueConstraint("equipment_id", "component_id", "coverage_type", name="uq_equipment_warranty_scope"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    equipment_id: int = Field(foreign_key="customer_equipment.id", index=True)
    component_id: Optional[int] = Field(default=None, foreign_key="equipment_component.id", index=True)
    policy_id: Optional[int] = Field(default=None, foreign_key="warranty_policy.id", index=True)
    coverage_type: str = Field(default="supplier", sa_column=Column(String(32), nullable=False, index=True))
    source: str = Field(default="policy", sa_column=Column(String(32), nullable=False, index=True))

    starts_at: Optional[datetime] = Field(default=None, index=True)
    expires_at: Optional[datetime] = Field(default=None, index=True)
    maintenance_required: bool = Field(default=False, index=True)
    maintenance_interval_months: Optional[int] = Field(default=None)
    grace_period_days: int = Field(default=0)
    allowed_maintenance_provider: str = Field(default="any", sa_column=Column(String(32), nullable=False))
    next_maintenance_due_at: Optional[datetime] = Field(default=None, index=True)
    terms_snapshot: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    policy_snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    decision_status: str = Field(default="none", sa_column=Column(String(32), nullable=False, index=True))
    decision_reason: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    decided_at: Optional[datetime] = Field(default=None, index=True)
    decided_by: Optional[str] = Field(default=None, sa_column=Column(String(160), nullable=True))
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})


class EquipmentWarrantyDecision(SQLModel, table=True):
    __tablename__ = "equipment_warranty_decision"

    id: Optional[int] = Field(default=None, primary_key=True)
    coverage_id: int = Field(foreign_key="equipment_warranty_coverage.id", index=True)
    action: str = Field(sa_column=Column(String(32), nullable=False, index=True))
    reason: str = Field(sa_column=Column(Text, nullable=False))
    decided_by: str = Field(sa_column=Column(String(160), nullable=False, index=True))
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class EquipmentMaintenanceReminder(SQLModel, table=True):
    __tablename__ = "equipment_maintenance_reminder"
    __table_args__ = (
        UniqueConstraint(
            "coverage_id",
            "reminder_type",
            "due_at",
            name="uq_equipment_maintenance_reminder_cycle",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    equipment_id: int = Field(foreign_key="customer_equipment.id", index=True)
    coverage_id: int = Field(foreign_key="equipment_warranty_coverage.id", index=True)
    reminder_type: str = Field(sa_column=Column(String(32), nullable=False, index=True))
    due_at: datetime = Field(index=True)
    status: str = Field(default="open", sa_column=Column(String(32), nullable=False, index=True))
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    resolved_at: Optional[datetime] = Field(default=None, index=True)
