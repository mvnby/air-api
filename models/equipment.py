from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Text
from sqlmodel import Field, Relationship, SQLModel

from .common import EquipmentServiceEventType


class CustomerEquipment(SQLModel, table=True):
    __tablename__ = "customer_equipment"

    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)
    customer_branch_id: Optional[int] = Field(default=None, foreign_key="customer_branches.id", index=True)

    equipment_type: str = Field(default="hvac", sa_column=Column(String, index=True))
    display_name: Optional[str] = Field(default=None, index=True)
    brand: Optional[str] = Field(default=None, index=True)
    model: Optional[str] = Field(default=None, index=True)
    serial: Optional[str] = Field(default=None, index=True)
    inventory_number: Optional[str] = Field(default=None, index=True)
    location_hint: Optional[str] = None
    refrigerant_type: Optional[str] = Field(default=None, index=True)
    notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    is_archived: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})

    customer: Optional["Customer"] = Relationship()
    customer_branch: Optional["CustomerBranch"] = Relationship()


class EquipmentServiceHistory(SQLModel, table=True):
    __tablename__ = "equipment_service_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    equipment_id: int = Field(foreign_key="customer_equipment.id", index=True)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id", index=True)

    event_type: EquipmentServiceEventType = Field(
        default=EquipmentServiceEventType.OTHER,
        sa_column=Column(String, index=True),
    )
    event_date: datetime = Field(default_factory=datetime.now, index=True)
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
