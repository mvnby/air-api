from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    text,
)
from sqlmodel import Field, Relationship, SQLModel

from .common import CustomerType, DocumentRoleType, LeadIntakeSource, LeadLossReason, LeadSegmentHint, LeadStatus


class Customer(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_customer_id_tenant"),
        Index("ix_customer_tenant_created_at", "tenant_id", "created_at"),
        Index("ix_customer_tenant_phone", "tenant_id", "phone"),
        Index("ix_customer_tenant_inn", "tenant_id", "inn"),
        CheckConstraint(
            "signing_mode IN ('self', 'statutory_body', 'power_of_attorney')",
            name="ck_customer_signing_mode_valid",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    tenant_id: int = Field(foreign_key="tenant.id", nullable=False)

    name: str = Field(index=True)
    phone: str = Field(index=True)
    email: Optional[str] = None
    type: CustomerType = Field(
        default=CustomerType.individual,
        sa_column=Column(String, nullable=False),
    )

    full_legal_name: Optional[str] = None
    inn: Optional[str] = Field(default=None, index=True)
    kpp: Optional[str] = None
    legal_address: Optional[str] = None
    actual_address: Optional[str] = None
    city: Optional[str] = None

    bank_name: Optional[str] = None
    bic: Optional[str] = None
    iban: Optional[str] = None

    signer_position: str = Field(default="директора")
    signer_name: Optional[str] = None
    acting_basis: str = Field(default="Устава")
    signing_mode: str = Field(default="self", sa_column=Column(String, nullable=False))

    created_at: datetime = Field(default_factory=datetime.now)
    is_archived: bool = Field(default=False, index=True)
    is_favorite: bool = Field(default=False, index=True)

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
    document_role_type: Optional[DocumentRoleType] = Field(default=None, sa_column=Column(String, nullable=True))
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
    customer_id: int = Field(
        foreign_key="customer.id",
        ondelete="CASCADE",
        index=True,
    )

    name: Optional[str] = None
    delivery_address: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None

    is_default: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})

    customer: Optional["Customer"] = Relationship(back_populates="branches")
    orders: List["Order"] = Relationship(back_populates="customer_branch")


class CustomerRequisitesRecognition(SQLModel, table=True):
    __tablename__ = "customer_requisites_recognition"
    __table_args__ = (
        Index(
            "uq_customer_requisites_telegram_message",
            "tenant_id",
            "source",
            "telegram_user_id",
            "telegram_chat_id",
            "telegram_message_id",
            unique=True,
            postgresql_where=text(
                "source IN ('telegram', 'telegram_text') "
                "AND telegram_user_id IS NOT NULL "
                "AND telegram_chat_id IS NOT NULL "
                "AND telegram_message_id IS NOT NULL"
            ),
            sqlite_where=text(
                "source IN ('telegram', 'telegram_text') "
                "AND telegram_user_id IS NOT NULL "
                "AND telegram_chat_id IS NOT NULL "
                "AND telegram_message_id IS NOT NULL"
            ),
        ),
        Index(
            "ix_customer_requisites_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
        ForeignKeyConstraint(
            ["duplicate_customer_id", "tenant_id"],
            ["customer.id", "customer.tenant_id"],
            name="fk_customer_requisites_duplicate_customer_tenant",
        ),
        ForeignKeyConstraint(
            ["confirmed_customer_id", "tenant_id"],
            ["customer.id", "customer.tenant_id"],
            name="fk_customer_requisites_confirmed_customer_tenant",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    # Recognition payloads contain customer PII and share the same tenant
    # boundary as the Customer they may create or update.
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False)

    source: str = Field(default="manager", index=True)
    status: str = Field(default="recognized", index=True)
    telegram_user_id: Optional[int] = Field(default=None, index=True)
    telegram_chat_id: Optional[int] = Field(default=None, index=True)
    telegram_message_id: Optional[int] = Field(default=None, index=True)

    original_filename: Optional[str] = None
    mime_type: Optional[str] = None
    local_file_path: Optional[str] = None
    local_file_url: Optional[str] = None

    raw_text: str = Field(default="")
    extracted_json: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False, default=dict))
    validation_flags: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False, default=dict))

    duplicate_customer_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True, index=True),
    )
    confirmed_customer_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True, index=True),
    )
    confirmed_action: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})
    confirmed_at: Optional[datetime] = None


class Lead(SQLModel, table=True):
    __table_args__ = (
        Index(
            "uq_lead_bot_source_fingerprint",
            "tenant_id",
            "source_fingerprint",
            unique=True,
            postgresql_where=text("source = 'bot' AND source_fingerprint IS NOT NULL"),
            sqlite_where=text("source = 'bot' AND source_fingerprint IS NOT NULL"),
        ),
        Index("ix_lead_tenant_status_created_at", "tenant_id", "status", "created_at"),
        Index("ix_lead_storefront_status_created_at", "storefront_id", "status", "created_at"),
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_lead_storefront_tenant",
        ),
        ForeignKeyConstraint(
            ["converted_order_id", "tenant_id", "storefront_id"],
            ["order.id", "order.tenant_id", "order.storefront_id"],
            name="fk_lead_converted_order_scope",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    tenant_id: int = Field(foreign_key="tenant.id", nullable=False)
    storefront_id: int = Field(sa_column=Column(Integer, nullable=False))

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
    source_message_id: Optional[str] = Field(default=None, index=True)
    source_fingerprint: Optional[str] = Field(default=None, index=True)

    next_followup_date: Optional[datetime] = None
    archived_at: Optional[datetime] = Field(default=None, index=True)

    converted_order_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})

    def __str__(self):
        return f"Lead #{self.id} ({self.status})"
