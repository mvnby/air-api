"""Daily aggregate counts only; no actor, order, text, coordinate or session data."""

from datetime import date
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlmodel import Field, SQLModel

USAGE_DIMENSIONS = (
    "tenant_id", "storefront_id", "day", "layout_version",
    "workflow", "party_kind", "viewport", "metric",
)


class OrderWorkspaceUsageDaily(SQLModel, table=True):
    __tablename__ = "order_workspace_usage_daily"
    __table_args__ = (
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"], ["storefront.id", "storefront.tenant_id"],
            name="fk_order_usage_storefront_tenant", ondelete="CASCADE",
        ),
        UniqueConstraint(*USAGE_DIMENSIONS, name="uq_order_usage_dimensions"),
        CheckConstraint("count > 0", name="ck_order_usage_positive_count"),
        Index("ix_order_usage_scope_day", "tenant_id", "storefront_id", "day"),
        Index("ix_order_usage_day_id", "day", "id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False)
    storefront_id: int = Field(sa_column=Column(Integer, nullable=False))
    day: date
    layout_version: str = Field(sa_column=Column(String(24), nullable=False))
    workflow: str = Field(sa_column=Column(String(24), nullable=False))
    party_kind: str = Field(sa_column=Column(String(32), nullable=False))
    viewport: str = Field(sa_column=Column(String(12), nullable=False))
    metric: str = Field(sa_column=Column(String(32), nullable=False))
    count: int = Field(sa_column=Column(BigInteger, nullable=False))
