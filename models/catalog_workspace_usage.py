"""Content-free daily aggregates for the Manager catalog pilot."""

from datetime import date
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, Column, Index, String, UniqueConstraint
from sqlmodel import Field, SQLModel


CATALOG_USAGE_DIMENSIONS = (
    "day", "layout_version", "device", "action", "outcome", "duration_bucket",
)


class CatalogWorkspaceUsageDaily(SQLModel, table=True):
    """Platform aggregate only; intentionally has no actor, product, or tenant reference."""

    __tablename__ = "catalog_workspace_usage_daily"
    __table_args__ = (
        UniqueConstraint(*CATALOG_USAGE_DIMENSIONS, name="uq_catalog_usage_dimensions"),
        CheckConstraint("count > 0", name="ck_catalog_usage_positive_count"),
        Index("ix_catalog_usage_day", "day"),
        Index("ix_catalog_usage_day_id", "day", "id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    day: date
    layout_version: str = Field(sa_column=Column(String(24), nullable=False))
    device: str = Field(sa_column=Column(String(12), nullable=False))
    action: str = Field(sa_column=Column(String(32), nullable=False))
    outcome: str = Field(sa_column=Column(String(16), nullable=False))
    duration_bucket: str = Field(sa_column=Column(String(16), nullable=False))
    count: int = Field(sa_column=Column(BigInteger, nullable=False))
