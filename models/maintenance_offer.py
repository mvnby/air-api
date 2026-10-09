"""Immutable commercial evidence and factual resolution of maintenance findings."""
from datetime import datetime
from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel
from models.maintenance_observation import utc_now


class MaintenanceOffer(SQLModel, table=True):
    __tablename__ = 'maintenance_offer'
    __table_args__ = (UniqueConstraint('continuation_id', 'command_key', name='uq_maintenance_offer_command'),)
    id: int | None = Field(default=None, primary_key=True)
    continuation_id: int = Field(foreign_key='maintenance_continuation.id', index=True)
    proposal_id: int = Field(foreign_key='order_proposal.id')
    command_key: str
    command_hash: str
    snapshot: dict = Field(sa_column=Column(JSON, nullable=False))
    created_by: str
    created_at: datetime = Field(default_factory=utc_now)


class MaintenanceOfferSource(SQLModel, table=True):
    __tablename__ = 'maintenance_offer_source'
    __table_args__ = (UniqueConstraint('offer_id', 'revision_id', name='uq_maintenance_offer_source'),)
    id: int | None = Field(default=None, primary_key=True)
    offer_id: int = Field(foreign_key='maintenance_offer.id', index=True)
    revision_id: int = Field(foreign_key='maintenance_observation_revision.id')


class MaintenanceOfferEvent(SQLModel, table=True):
    __tablename__ = 'maintenance_offer_event'
    __table_args__ = (UniqueConstraint('offer_id', 'command_key', name='uq_maintenance_offer_event_command'),
                     UniqueConstraint('offer_id', 'version', name='uq_maintenance_offer_event_version'))
    id: int | None = Field(default=None, primary_key=True)
    offer_id: int = Field(foreign_key='maintenance_offer.id', index=True)
    version: int
    action: str
    command_key: str
    command_hash: str
    details: dict = Field(sa_column=Column(JSON, nullable=False))
    actor: str
    occurred_at: datetime
    created_at: datetime = Field(default_factory=utc_now)


class MaintenanceResolution(SQLModel, table=True):
    __tablename__ = 'maintenance_resolution'
    id: int | None = Field(default=None, primary_key=True)
    observation_id: int = Field(foreign_key='maintenance_observation.id', unique=True)
    revision_id: int = Field(foreign_key='maintenance_observation_revision.id')
    offer_id: int = Field(foreign_key='maintenance_offer.id')
    history_id: int | None = Field(default=None, foreign_key='equipment_service_history.id')
    command_key: str
    command_hash: str
    evidence: str
    actor: str
    resolved_at: datetime
    created_at: datetime = Field(default_factory=utc_now)
