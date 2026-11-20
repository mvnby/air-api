"""Order-level locations and the physical units covered at each location."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, ForeignKeyConstraint, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class OrderSite(SQLModel, table=True):
    __tablename__ = "order_site"
    __table_args__ = (
        UniqueConstraint("order_id", "id", name="uq_order_site_order_id"),
        UniqueConstraint("order_id", "customer_branch_id", name="uq_order_site_order_branch"),
        CheckConstraint("version >= 1", name="ck_order_site_version"),
    )

    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", ondelete="CASCADE", index=True)
    customer_id: int = Field(foreign_key="customer.id")
    customer_branch_id: int | None = Field(
        default=None, foreign_key="customer_branches.id", ondelete="SET NULL", index=True,
    )
    title: str = Field(sa_column=Column(Text, nullable=False))
    address: str = Field(sa_column=Column(Text, nullable=False))
    version: int = Field(default=1)
    created_at: datetime = Field(default_factory=datetime.now)


class OrderSiteEquipment(SQLModel, table=True):
    __tablename__ = "order_site_equipment"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "site_id"],
            ["order_site.order_id", "order_site.id"],
            name="fk_order_site_equipment_site",
            ondelete="CASCADE",
        ),
        UniqueConstraint("order_id", "equipment_id", name="uq_order_site_equipment_order_unit"),
        UniqueConstraint(
            "order_id", "site_id", "equipment_id", name="uq_order_site_equipment_order_site_unit",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    order_id: int
    site_id: int = Field(index=True)
    equipment_id: int = Field(foreign_key="customer_equipment.id", index=True)
    role: str
    created_at: datetime = Field(default_factory=datetime.now)
