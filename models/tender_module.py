from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Integer, JSON, false, text
from sqlmodel import Field, SQLModel

from models.tenancy import utc_now


class TenantTenderModule(SQLModel, table=True):
    """Company-owned tender preferences with platform-controlled access."""

    __tablename__ = "tenant_tender_module"
    __table_args__ = (CheckConstraint("NOT enabled OR entitled", name="ck_tender_module_entitled"),)

    tenant_id: int = Field(primary_key=True, foreign_key="tenant.id", ondelete="CASCADE")
    entitled: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default=false()))
    enabled: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default=false()))
    profiles: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    version: int = Field(default=1, sa_column=Column(Integer, nullable=False, server_default=text("1")))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
