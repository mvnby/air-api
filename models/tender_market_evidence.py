from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, JSON, String
from sqlmodel import Field, SQLModel

from models.tenancy import utc_now


class TenderMarketEvidence(SQLModel, table=True):
    """A shared receipt containing evidence from public source originals."""

    __tablename__ = "tender_market_evidence"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'reading', 'completed', 'failed')", name="ck_tender_market_evidence_status"),
        Index("ix_tender_market_evidence_queue", "status", "available_at"),
    )

    publication_id: int = Field(primary_key=True, foreign_key="tender_market_publication.id", ondelete="CASCADE")
    source_revision: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    reader_version: int = Field(sa_column=Column(Integer, nullable=False))
    status: str = Field(default="queued", sa_column=Column(String(20), nullable=False))
    attempts: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    available_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    lease_until: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    lease_token: str | None = Field(default=None, sa_column=Column(String(32)))
    checked_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    fingerprint: str | None = Field(default=None, sa_column=Column(String(64)))
    documents_source_url: str | None = Field(default=None, sa_column=Column(String(2048)))
    report: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    error: str | None = Field(default=None, sa_column=Column(String(300)))
