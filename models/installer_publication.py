"""Manager publications for one company-scoped installer assignment."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel


class InstallerMaterialPublication(SQLModel, table=True):
    __tablename__ = "installer_material_publication"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "order_attachment_link_id",
            name="uq_installer_material_assignment_link",
        ),
        ForeignKeyConstraint(
            ["assignment_id", "tenant_id", "storefront_id", "order_id"],
            [
                "order_work_assignment.id",
                "order_work_assignment.tenant_id",
                "order_work_assignment.storefront_id",
                "order_work_assignment.order_id",
            ],
            name="fk_installer_material_assignment_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["order_attachment_link_id", "order_id"],
            ["order_attachment_link.id", "order_attachment_link.order_id"],
            name="fk_installer_material_order_link",
            ondelete="RESTRICT",
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(index=True)
    storefront_id: int
    order_id: int = Field(index=True)
    assignment_id: int = Field(index=True)
    order_attachment_link_id: int
    created_at: datetime = Field(default_factory=datetime.now)
    revoked_at: datetime | None = None


class InstallerCollectionInstruction(SQLModel, table=True):
    __tablename__ = "installer_collection_instruction"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_installer_collection_order"),
        ForeignKeyConstraint(
            ["order_id", "tenant_id", "storefront_id"],
            ["order.id", "order.tenant_id", "order.storefront_id"],
            name="fk_installer_collection_order_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["assignment_id", "tenant_id", "storefront_id", "order_id"],
            [
                "order_work_assignment.id",
                "order_work_assignment.tenant_id",
                "order_work_assignment.storefront_id",
                "order_work_assignment.order_id",
            ],
            name="fk_installer_collection_assignment_scope",
            ondelete="CASCADE",
        ),
        CheckConstraint("version >= 0", name="ck_installer_collection_version"),
        CheckConstraint(
            "amount IS NULL OR amount >= 0", name="ck_installer_collection_amount"
        ),
        CheckConstraint(
            "currency IS NULL OR currency IN ('BYN','USD','EUR')",
            name="ck_installer_collection_currency",
        ),
        CheckConstraint(
            "(assignment_id IS NULL AND amount IS NULL AND currency IS NULL) OR (assignment_id IS NOT NULL AND amount IS NOT NULL AND currency IS NOT NULL)",
            name="ck_installer_collection_complete",
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(index=True)
    storefront_id: int
    order_id: int
    assignment_id: int | None = None
    amount: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(14, 2), nullable=True)
    )
    currency: str | None = Field(
        default=None, sa_column=Column(String(3), nullable=True)
    )
    financial_fingerprint: str = Field(
        default="", sa_column=Column(String(64), nullable=False)
    )
    version: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    updated_at: datetime = Field(default_factory=datetime.now)
