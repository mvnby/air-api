"""Frozen pay commitments and immutable, exactly allocated settlements."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlmodel import Field, SQLModel

from models.worker_money import now


class WorkerPayAgreement(SQLModel, table=True):
    __tablename__ = "worker_pay_agreement"
    __table_args__ = (
        UniqueConstraint("id", "account_id", name="uq_worker_pay_agreement_account"),
        ForeignKeyConstraint(
            ["account_id", "tenant_id", "storefront_id"],
            [
                "worker_cash_account.id",
                "worker_cash_account.tenant_id",
                "worker_cash_account.storefront_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["order_id", "tenant_id", "storefront_id"],
            ["order.id", "order.tenant_id", "order.storefront_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "uq_worker_pay_active_work",
            "account_id",
            "order_id",
            "work_key",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
            sqlite_where=text("status <> 'cancelled'"),
        ),
        CheckConstraint(
            "amount > 0 AND cost_byn_amount > 0", name="ck_worker_pay_agreement_amount"
        ),
        CheckConstraint(
            "currency IN ('BYN','USD','EUR')", name="ck_worker_pay_agreement_currency"
        ),
        CheckConstraint(
            "status IN ('agreed','accrued','cancelled')",
            name="ck_worker_pay_agreement_status",
        ),
        CheckConstraint("version >= 0", name="ck_worker_pay_agreement_version"),
    )
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(index=True)
    tenant_id: int
    storefront_id: int
    order_id: int = Field(index=True)
    assignment_reference: int
    work_stage_id: int | None = None
    work_key: str = Field(sa_column=Column(String(64), nullable=False))
    title: str = Field(sa_column=Column(String(160), nullable=False))
    amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    currency: str = Field(sa_column=Column(String(3), nullable=False))
    cost_byn_amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    status: str = Field(default="agreed", sa_column=Column(String(16), nullable=False))
    version: int = 0
    created_at: datetime = Field(
        default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    accrued_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    cancelled_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    cancellation_reason: str | None = Field(default=None, sa_column=Column(String(500)))


class WorkerPayPayout(SQLModel, table=True):
    __tablename__ = "worker_pay_payout"
    __table_args__ = (
        UniqueConstraint("id", "account_id", name="uq_worker_pay_payout_account"),
        ForeignKeyConstraint(
            ["account_id", "tenant_id", "storefront_id"],
            [
                "worker_cash_account.id",
                "worker_cash_account.tenant_id",
                "worker_cash_account.storefront_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="ck_worker_pay_payout_amount"),
        CheckConstraint(
            "currency IN ('BYN','USD','EUR')", name="ck_worker_pay_payout_currency"
        ),
        CheckConstraint(
            "method IN ('cash','bank','offset')", name="ck_worker_pay_payout_method"
        ),
        CheckConstraint(
            "(reversed_at IS NULL AND reversal_reason IS NULL) OR (reversed_at IS NOT NULL AND reversal_reason IS NOT NULL)",
            name="ck_worker_pay_payout_reversal",
        ),
        CheckConstraint("version >= 0", name="ck_worker_pay_payout_version"),
    )
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(index=True)
    tenant_id: int
    storefront_id: int
    amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    currency: str = Field(sa_column=Column(String(3), nullable=False))
    method: str = Field(sa_column=Column(String(16), nullable=False))
    version: int = 0
    created_at: datetime = Field(
        default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    reversed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    reversal_reason: str | None = Field(default=None, sa_column=Column(String(500)))


class WorkerPayPayoutAllocation(SQLModel, table=True):
    __tablename__ = "worker_pay_payout_allocation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["payout_id", "account_id"],
            ["worker_pay_payout.id", "worker_pay_payout.account_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["agreement_id", "account_id"],
            ["worker_pay_agreement.id", "worker_pay_agreement.account_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="ck_worker_pay_payout_allocation_amount"),
    )
    payout_id: int = Field(primary_key=True)
    agreement_id: int = Field(primary_key=True)
    account_id: int = Field(index=True)
    amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))


class WorkerPayOffsetCashAllocation(SQLModel, table=True):
    __tablename__ = "worker_pay_offset_cash_allocation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["payout_id", "account_id"],
            ["worker_pay_payout.id", "worker_pay_payout.account_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["receipt_id", "account_id"],
            ["worker_cash_receipt.id", "worker_cash_receipt.account_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="ck_worker_pay_offset_cash_amount"),
    )
    payout_id: int = Field(primary_key=True)
    receipt_id: int = Field(primary_key=True)
    account_id: int = Field(index=True)
    amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
