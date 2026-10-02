"""Personal read markers and auditable Order inbox decisions."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKeyConstraint, Index, Integer, String, Text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InboxReadState(SQLModel, table=True):
    __tablename__ = "inbox_read_state"
    __table_args__ = (
        ForeignKeyConstraint(["order_id", "tenant_id", "storefront_id"],
                             ["order.id", "order.tenant_id", "order.storefront_id"],
                             name="fk_inbox_read_order_scope", ondelete="CASCADE"),
        CheckConstraint("(entity_kind = 'order' AND order_id IS NOT NULL AND order_id = entity_id AND lead_id IS NULL) OR "
                        "(entity_kind = 'lead' AND lead_id IS NOT NULL AND lead_id = entity_id AND order_id IS NULL)",
                        name="ck_inbox_read_identity"),
    )
    tenant_id: int = Field(foreign_key="tenant.id", primary_key=True)
    username: str = Field(sa_column=Column(String(120), primary_key=True))
    entity_kind: str = Field(sa_column=Column(String(12), primary_key=True))
    entity_id: int = Field(primary_key=True)
    storefront_id: int = Field(sa_column=Column(Integer, nullable=False))
    order_id: Optional[int] = Field(default=None)
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id", ondelete="CASCADE")
    is_read: bool = Field(default=False)
    read_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class InboxTriageState(SQLModel, table=True):
    __tablename__ = "inbox_triage_state"
    __table_args__ = (
        ForeignKeyConstraint(["order_id", "tenant_id", "storefront_id"],
                             ["order.id", "order.tenant_id", "order.storefront_id"],
                             name="fk_inbox_state_order_scope", ondelete="CASCADE"),
        CheckConstraint("outcome IS NULL OR outcome IN ('refusal', 'spam', 'duplicate', 'deadline_expired')",
                        name="ck_inbox_state_outcome"),
        CheckConstraint("(entity_kind = 'order' AND order_id IS NOT NULL AND order_id = entity_id AND lead_id IS NULL) OR "
                        "(entity_kind = 'lead' AND lead_id IS NOT NULL AND lead_id = entity_id AND order_id IS NULL)",
                        name="ck_inbox_state_identity"),
        Index("ix_inbox_state_scope_archive", "tenant_id", "storefront_id", "archived_at"),
    )
    entity_kind: str = Field(sa_column=Column(String(12), primary_key=True))
    entity_id: int = Field(primary_key=True)
    order_id: Optional[int] = Field(default=None)
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id", ondelete="CASCADE")
    tenant_id: int = Field(foreign_key="tenant.id")
    storefront_id: int
    outcome: Optional[str] = Field(default=None, sa_column=Column(String(32)))
    reason: Optional[str] = Field(default=None, sa_column=Column(String(32)))
    note: Optional[str] = Field(default=None, sa_column=Column(Text))
    archived_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    archived_by: Optional[str] = Field(default=None, sa_column=Column(String(120)))
    # Restoring an expired tender suppresses that exact deadline permanently.
    # A newly published deadline has a new identity and can expire normally.
    restored_deadline_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class InboxEvent(SQLModel, table=True):
    __tablename__ = "inbox_event"
    __table_args__ = (
        ForeignKeyConstraint(["order_id", "tenant_id", "storefront_id"],
                             ["order.id", "order.tenant_id", "order.storefront_id"],
                             name="fk_inbox_event_order_scope", ondelete="CASCADE"),
        CheckConstraint("(entity_kind = 'order' AND order_id IS NOT NULL AND order_id = entity_id AND lead_id IS NULL) OR "
                        "(entity_kind = 'lead' AND lead_id IS NOT NULL AND lead_id = entity_id AND order_id IS NULL)",
                        name="ck_inbox_event_identity"),
        Index("ix_inbox_event_entity_created", "entity_kind", "entity_id", "created_at", "id"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    entity_kind: str = Field(sa_column=Column(String(12), nullable=False))
    entity_id: int
    order_id: Optional[int] = Field(default=None)
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id", ondelete="CASCADE")
    tenant_id: int = Field(foreign_key="tenant.id")
    storefront_id: int
    kind: str = Field(sa_column=Column(String(24), nullable=False))
    actor: str = Field(sa_column=Column(String(120), nullable=False))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    note: Optional[str] = Field(default=None, sa_column=Column(Text))
    outcome: Optional[str] = Field(default=None, sa_column=Column(String(32)))
    reason: Optional[str] = Field(default=None, sa_column=Column(String(32)))
    next_followup_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
