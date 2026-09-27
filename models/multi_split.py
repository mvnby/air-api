"""Persistence models for reviewed multi-split configurations."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import CheckConstraint, Column, DateTime, JSON, String, UniqueConstraint
from sqlmodel import Field, SQLModel


COMPATIBILITY_PROFILE_VERIFICATION_STATUSES = ("draft", "verified")
CONFIGURATION_VERIFICATION_STATUSES = (
    "draft",
    "confirmed",
    "requires_specialist",
    "incompatible",
)


class MultiSplitCompatibilityProfile(SQLModel, table=True):
    """Manufacturer-backed compatibility data for one outdoor unit."""

    __tablename__ = "multi_split_compatibility_profile"
    __table_args__ = (
        UniqueConstraint(
            "outdoor_product_id",
            name="uq_multi_split_compatibility_profile_outdoor_product",
        ),
        CheckConstraint(
            "verification_status IN ('draft', 'verified')",
            name="ck_multi_split_compatibility_profile_verification_status",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_multi_split_compatibility_profile_version_positive",
        ),
        CheckConstraint(
            "max_indoor_units IS NULL OR max_indoor_units > 0",
            name="ck_multi_split_compatibility_profile_max_indoor_units_positive",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    outdoor_product_id: int = Field(foreign_key="product.id", index=True)
    verification_status: str = Field(
        default="draft",
        sa_column=Column(String(24), nullable=False, index=True),
    )
    source_url: Optional[str] = Field(default=None, sa_column=Column(String(1000)))
    source_version: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    version: int = Field(default=1)
    verified_at: Optional[datetime] = Field(default=None, index=True)
    verified_by: Optional[str] = Field(default=None, sa_column=Column(String(120)))
    max_indoor_units: Optional[int] = Field(default=None)
    allowed_indoor_product_ids: list[int] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    exact_combinations: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    mandatory_component_product_ids: list[int] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime, nullable=False, onupdate=datetime.now),
    )


class OrderMultiSplitConfiguration(SQLModel, table=True):
    """The component selection kept with one order proposal."""

    __tablename__ = "order_multi_split_configuration"
    __table_args__ = (
        UniqueConstraint(
            "proposal_id",
            name="uq_order_multi_split_configuration_proposal",
        ),
        CheckConstraint(
            "verification_status IN ('draft', 'confirmed', 'requires_specialist', 'incompatible')",
            name="ck_order_multi_split_configuration_verification_status",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", index=True)
    proposal_id: int = Field(foreign_key="order_proposal.id", index=True)
    rooms: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    component_snapshot: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    verification_status: str = Field(
        default="draft",
        sa_column=Column(String(32), nullable=False, index=True),
    )
    profile_id: Optional[int] = Field(
        default=None,
        foreign_key="multi_split_compatibility_profile.id",
        index=True,
    )
    profile_version: Optional[int] = Field(default=None)
    source_url: Optional[str] = Field(default=None, sa_column=Column(String(1000)))
    source_version: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime, nullable=False, onupdate=datetime.now),
    )


class LeadMultiSplitConfiguration(SQLModel, table=True):
    """Structured public multi-split selection attached to one lead."""

    __tablename__ = "lead_multi_split_configuration"
    __table_args__ = (
        UniqueConstraint("lead_id", name="uq_lead_multi_split_configuration_lead"),
        CheckConstraint(
            "verification_status IN ('draft', 'confirmed', 'requires_specialist', 'incompatible')",
            name="ck_lead_multi_split_configuration_verification_status",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    rooms: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    component_snapshot: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    verification_status: str = Field(
        default="draft",
        sa_column=Column(String(32), nullable=False, index=True),
    )
    profile_id: Optional[int] = Field(
        default=None,
        foreign_key="multi_split_compatibility_profile.id",
        index=True,
    )
    profile_version: Optional[int] = Field(default=None)
    source_url: Optional[str] = Field(default=None, sa_column=Column(String(1000)))
    source_version: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime, nullable=False),
    )
