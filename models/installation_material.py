from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, Date, Numeric, String, UniqueConstraint
from sqlmodel import Field, SQLModel


class InstallationMaterialPrice(SQLModel, table=True):
    __tablename__ = "installation_material_price"
    __table_args__ = (
        UniqueConstraint("tenant_id", "title", "supplier", name="uq_installation_material_price_item"),
        CheckConstraint("pack_quantity > 0 AND pack_price_byn > 0", name="ck_installation_material_price_amounts"),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id")
    title: str = Field(sa_column=Column(String(180), nullable=False))
    supplier: str = Field(sa_column=Column(String(120), nullable=False))
    unit: str = Field(sa_column=Column(String(8), nullable=False))
    pack_quantity: Decimal = Field(sa_column=Column(Numeric(12, 4), nullable=False))
    pack_price_byn: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    checked_on: date = Field(sa_column=Column(Date, nullable=False))
    source_url: str | None = Field(default=None, sa_column=Column(String(2083)))
    note: str = Field(default="", sa_column=Column(String(500), nullable=False))
    version: int = 1
