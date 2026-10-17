"""Cash custody is independent of live work grants and installer remuneration."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel


def now():
    return datetime.now(timezone.utc)


class WorkerCashAccount(SQLModel, table=True):
    __tablename__ = "worker_cash_account"
    __table_args__ = (
        UniqueConstraint(
            "worker_profile_id", "storefront_id", name="uq_worker_cash_profile_site"
        ),
        UniqueConstraint(
            "id", "tenant_id", "storefront_id", name="uq_worker_cash_account_scope"
        ),
        ForeignKeyConstraint(
            ["worker_profile_id", "tenant_id"],
            ["tenant_worker_profile.id", "tenant_worker_profile.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 0", name="ck_worker_cash_account_version"),
    )
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(index=True)
    storefront_id: int = Field(index=True)
    worker_profile_id: int = Field(index=True)
    version: int = Field(default=0)


class WorkerCashReceipt(SQLModel, table=True):
    __tablename__ = "worker_cash_receipt"
    __table_args__ = (
        UniqueConstraint("id", "account_id", name="uq_worker_cash_receipt_account"),
        UniqueConstraint(
            "order_id", "collection_version", name="uq_worker_cash_receipt_instruction"
        ),
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
        ForeignKeyConstraint(
            ["payment_id", "order_id"],
            ["payment.id", "payment.order_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["reversal_payment_id", "order_id"],
            ["payment.id", "payment.order_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="ck_worker_cash_receipt_amount"),
        CheckConstraint(
            "collection_version >= 0", name="ck_worker_cash_receipt_version"
        ),
        CheckConstraint(
            "currency IN ('BYN','USD','EUR')", name="ck_worker_cash_receipt_currency"
        ),
        CheckConstraint(
            "(reversal_payment_id IS NULL AND reversed_at IS NULL AND reversal_reason IS NULL) OR (reversal_payment_id IS NOT NULL AND reversed_at IS NOT NULL AND reversal_reason IS NOT NULL)",
            name="ck_worker_cash_receipt_reversal",
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(index=True)
    tenant_id: int
    storefront_id: int
    order_id: int = Field(index=True)
    # Immutable reference, deliberately not an access-grant FK: deleting a visit
    # must preserve the financial record without retaining access to its order.
    assignment_reference: int
    collection_version: int
    amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    currency: str = Field(sa_column=Column(String(3), nullable=False))
    title: str = Field(sa_column=Column(String(160), nullable=False))
    payment_id: int = Field(unique=True)
    created_at: datetime = Field(
        default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    reversal_payment_id: int | None = Field(default=None, unique=True)
    reversed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
    reversal_reason: str | None = Field(default=None, sa_column=Column(String(500)))


class WorkerCashHandover(SQLModel, table=True):
    __tablename__ = "worker_cash_handover"
    __table_args__ = (
        UniqueConstraint("id", "account_id", name="uq_worker_cash_handover_account"),
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
            ["tenant_id", "recipient_staff_user_id"],
            ["tenant_membership.tenant_id", "tenant_membership.staff_user_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="ck_worker_cash_handover_amount"),
        CheckConstraint(
            "currency IN ('BYN','USD','EUR')", name="ck_worker_cash_handover_currency"
        ),
        CheckConstraint(
            "status IN ('pending','confirmed','rejected','cancelled')",
            name="ck_worker_cash_handover_status",
        ),
        CheckConstraint("version >= 0", name="ck_worker_cash_handover_version"),
        CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL) OR (status <> 'pending' AND resolved_at IS NOT NULL)",
            name="ck_worker_cash_handover_resolution",
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(index=True)
    tenant_id: int
    storefront_id: int
    recipient_staff_user_id: int
    recipient_name: str = Field(sa_column=Column(String(160), nullable=False))
    amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    currency: str = Field(sa_column=Column(String(3), nullable=False))
    status: str = Field(default="pending", sa_column=Column(String(16), nullable=False))
    version: int = Field(default=0)
    created_at: datetime = Field(
        default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    resolved_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )


class WorkerCashHandoverAllocation(SQLModel, table=True):
    __tablename__ = "worker_cash_handover_allocation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["handover_id", "account_id"],
            ["worker_cash_handover.id", "worker_cash_handover.account_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["receipt_id", "account_id"],
            ["worker_cash_receipt.id", "worker_cash_receipt.account_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="ck_worker_cash_handover_allocation_amount"),
    )
    handover_id: int = Field(primary_key=True)
    receipt_id: int = Field(primary_key=True)
    account_id: int = Field(index=True)
    amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))


class WorkerMoneyCommand(SQLModel, table=True):
    __tablename__ = "worker_money_command"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "idempotency_key", name="uq_worker_money_command_key"
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="worker_cash_account.id", index=True)
    actor_staff_user_id: int = Field(foreign_key="staff_users.id")
    idempotency_key: str = Field(sa_column=Column(String(36), nullable=False))
    request_hash: str = Field(sa_column=Column(String(64), nullable=False))
    result: dict = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
