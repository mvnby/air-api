from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Column, String, Text
from sqlmodel import Field, Relationship, SQLModel

from .common import EquipmentServiceEventType


class CustomerEquipment(SQLModel, table=True):
    __tablename__ = "customer_equipment"
    __table_args__ = (
        CheckConstraint(
            "warranty_mode IN ('auto', 'manual', 'none')",
            name="ck_customer_equipment_warranty_mode",
        ),
        CheckConstraint(
            "warranty_duration_months IS NULL OR "
            "(warranty_duration_months >= 1 AND warranty_duration_months <= 240)",
            name="ck_customer_equipment_warranty_duration_months",
        ),
        CheckConstraint(
            "maintenance_interval_months >= 1 AND maintenance_interval_months <= 120",
            name="ck_customer_equipment_maintenance_interval_months",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)
    customer_branch_id: Optional[int] = Field(default=None, foreign_key="customer_branches.id", index=True)
    catalog_product_id: Optional[int] = Field(default=None, foreign_key="product.id", index=True)
    source_order_id: Optional[int] = Field(default=None, foreign_key="order.id", index=True)

    equipment_type: str = Field(
        default="hvac",
        sa_column=Column(String, index=True, nullable=False),
    )
    equipment_source: str = Field(
        default="unknown",
        sa_column=Column(String, index=True, nullable=False),
    )
    display_name: Optional[str] = Field(default=None, index=True)
    brand: Optional[str] = Field(default=None, index=True)
    model: Optional[str] = Field(default=None, index=True)
    serial: Optional[str] = Field(default=None, index=True)
    inventory_number: Optional[str] = Field(default=None, index=True)
    location_hint: Optional[str] = None
    refrigerant_type: Optional[str] = Field(default=None, index=True)
    installed_at: Optional[datetime] = Field(default=None, index=True)
    commissioned_at: Optional[datetime] = Field(default=None, index=True)
    warranty_mode: str = Field(
        default="auto",
        sa_column=Column(String(16), nullable=False, index=True),
    )
    warranty_duration_months: Optional[int] = Field(default=None)
    warranty_started_at: Optional[datetime] = Field(default=None, index=True)
    warranty_expires_at: Optional[datetime] = Field(default=None, index=True)
    warranty_terms: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    maintenance_enabled: bool = Field(default=False, index=True)
    maintenance_interval_months: int = Field(default=12)
    maintenance_anchor_at: Optional[datetime] = Field(default=None, index=True)
    notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    is_archived: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})

    customer: Optional["Customer"] = Relationship()
    customer_branch: Optional["CustomerBranch"] = Relationship()


class EquipmentComponent(SQLModel, table=True):
    __tablename__ = "equipment_component"

    id: Optional[int] = Field(default=None, primary_key=True)
    equipment_id: int = Field(foreign_key="customer_equipment.id", index=True)
    catalog_product_id: Optional[int] = Field(default=None, foreign_key="product.id", index=True)
    supplier_id: Optional[int] = Field(default=None, foreign_key="supplier.id", index=True)

    component_type: str = Field(
        default="other",
        sa_column=Column(String, index=True, nullable=False),
    )
    title: Optional[str] = Field(default=None, index=True)
    brand: Optional[str] = Field(default=None, index=True)
    model: Optional[str] = Field(default=None, index=True)
    serial: Optional[str] = Field(default=None, index=True)
    inventory_number: Optional[str] = Field(default=None, index=True)
    supplier_invoice_number: Optional[str] = Field(default=None, index=True)
    supplier_invoice_date: Optional[datetime] = Field(default=None, index=True)
    notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    is_archived: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})

    equipment: Optional[CustomerEquipment] = Relationship()
    product: Optional["Product"] = Relationship()
    supplier: Optional["Supplier"] = Relationship()


class EquipmentServiceHistory(SQLModel, table=True):
    __tablename__ = "equipment_service_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    equipment_id: int = Field(foreign_key="customer_equipment.id", index=True)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id", index=True)

    event_type: EquipmentServiceEventType = Field(
        default=EquipmentServiceEventType.OTHER,
        sa_column=Column(String, index=True, nullable=False),
    )
    event_date: datetime = Field(default_factory=datetime.now, index=True)
    maintenance_provider: Optional[str] = Field(default=None, index=True)
    complaint_snapshot: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    diagnostic_result: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    repair_recommendation: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    refrigerant_type: Optional[str] = Field(default=None, index=True)
    refrigerant_amount: Optional[str] = None
    not_repairable: bool = Field(default=False, index=True)
    not_repairable_reason: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})

    equipment: Optional[CustomerEquipment] = Relationship()
    order: Optional["Order"] = Relationship()
