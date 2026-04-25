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
    is_archived: bool = Field(default=False, index=True)

    orders: List["Order"] = Relationship(back_populates="customer")
    contracts: List["CustomerContract"] = Relationship(
        back_populates="customer",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )
    branches: List["CustomerBranch"] = Relationship(
        back_populates="customer",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )

    def __str__(self):
        return self.name


class CustomerContract(SQLModel, table=True):
    __tablename__ = "customer_contract"

    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)

    number: str = Field(index=True)
    valid_from: datetime = Field(default_factory=datetime.now, index=True)
    valid_until: datetime = Field(index=True)
    status: str = Field(default="active", sa_column=Column(String, index=True))

    template_id: Optional[str] = None
    google_file_id: Optional[str] = None
    google_edit_url: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})

    customer: Optional["Customer"] = Relationship(back_populates="contracts")
    orders: List["Order"] = Relationship(back_populates="customer_contract")

    def __str__(self):
        return f"Договор {self.number}"


class CustomerBranch(SQLModel, table=True):
    __tablename__ = "customer_branches"

    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)

    name: Optional[str] = None
    delivery_address: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None

    is_default: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})

    customer: Optional["Customer"] = Relationship(back_populates="branches")
    orders: List["Order"] = Relationship(back_populates="customer_branch")


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
