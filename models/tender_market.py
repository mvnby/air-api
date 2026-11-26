from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, JSON, String, UniqueConstraint
from sqlmodel import Field, SQLModel


class TenderMarketPublication(SQLModel, table=True):
    """Public source facts retained independently of any company's CRM."""

    __tablename__ = "tender_market_publication"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_tender_market_native_identity"),
        Index("ix_tender_market_active_page", "active", "id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    source: str = Field(sa_column=Column(String(40), nullable=False))
    external_id: str = Field(sa_column=Column(String(300), nullable=False))
    source_url: str = Field(sa_column=Column(String(2048), nullable=False))
    canonical_url: str | None = Field(default=None, sa_column=Column(String(2048), nullable=True))
    title: str = Field(sa_column=Column(String(1000), nullable=False))
    active: bool = Field(sa_column=Column(Boolean, nullable=False))
    published_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    deadline_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    provider_updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    seen_generation: int = Field(sa_column=Column(Integer, nullable=False))
    lot_snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class TenderMarketCheckpoint(SQLModel, table=True):
    __tablename__ = "tender_market_checkpoint"

    id: int = Field(primary_key=True)
    cursor: str | None = Field(default=None, sa_column=Column(String(2048), nullable=True))
    generation: int = Field(default=1, sa_column=Column(Integer, nullable=False))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
