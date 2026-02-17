from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, String
from sqlmodel import Field, Relationship, SQLModel

from .common import CustomerType, LeadIntakeSource, LeadLossReason, LeadSegmentHint, LeadStatus


class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    name: str = Field(index=True)
    phone: str = Field(index=True)
    email: Optional[str] = None
    type: CustomerType = Field(default=CustomerType.individual)

    full_legal_name: Optional[str] = None
    inn: Optional[str] = Field(default=None, index=True)
    kpp: Optional[str] = None
    legal_address: Optional[str] = None
    actual_address: Optional[str] = None

    bank_name: Optional[str] = None
    bic: Optional[str] = None
    iban: Optional[str] = None

    signer_position: str = Field(default="директора")
    signer_name: Optional[str] = None
    acting_basis: str = Field(default="Устава")

    created_at: datetime = Field(default_factory=datetime.now)

    orders: List["Order"] = Relationship(back_populates="customer")

    def __str__(self):
        return self.name


class Lead(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    status: LeadStatus = Field(default=LeadStatus.new, sa_column=Column(String, index=True))
    source: LeadIntakeSource = Field(default=LeadIntakeSource.manager, sa_column=Column(String, index=True))
    segment_hint: LeadSegmentHint = Field(default=LeadSegmentHint.unknown, sa_column=Column(String, index=True))
    loss_reason: Optional[LeadLossReason] = Field(default=None, sa_column=Column(String, index=True, nullable=True))

    name: Optional[str] = None
    phone: Optional[str] = Field(default=None, index=True)
    email: Optional[str] = Field(default=None, index=True)
    inn: Optional[str] = Field(default=None, index=True)
    company_name: Optional[str] = None
    request_text: str = Field(default="")

    next_followup_date: Optional[datetime] = None
    archived_at: Optional[datetime] = Field(default=None, index=True)

    converted_order_id: Optional[int] = Field(default=None, foreign_key="order.id")

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})

    def __str__(self):
        return f"Lead #{self.id} ({self.status})"
