"""Frozen worker remuneration and explicit settlements; preserve all financial history."""

from alembic import op
import sqlalchemy as sa

revision = "w20261017pay02"
down_revision = "w20261017cash01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "order",
        sa.Column(
            "worker_pay_cost_byn", sa.Numeric(14, 2), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "worker_cash_handover", sa.Column("reversed_at", sa.DateTime(timezone=True))
    )
    op.add_column("worker_cash_handover", sa.Column("reversal_reason", sa.String(500)))
    op.drop_constraint(
        "ck_worker_cash_handover_status", "worker_cash_handover", type_="check"
    )
    op.create_check_constraint(
        "ck_worker_cash_handover_status",
        "worker_cash_handover",
        "status IN ('pending','confirmed','rejected','cancelled','reversed')",
    )
    op.create_check_constraint(
        "ck_worker_cash_handover_reversal",
        "worker_cash_handover",
        "(status = 'reversed' AND reversed_at IS NOT NULL AND reversal_reason IS NOT NULL) OR (status <> 'reversed' AND reversed_at IS NULL AND reversal_reason IS NULL)",
    )
    op.create_table(
        "worker_pay_agreement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("assignment_reference", sa.Integer(), nullable=False),
        sa.Column("work_stage_id", sa.Integer()),
        sa.Column("work_key", sa.String(64), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("cost_byn_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accrued_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancellation_reason", sa.String(500)),
        sa.UniqueConstraint("id", "account_id", name="uq_worker_pay_agreement_account"),
        sa.ForeignKeyConstraint(
            ["account_id", "tenant_id", "storefront_id"],
            [
                "worker_cash_account.id",
                "worker_cash_account.tenant_id",
                "worker_cash_account.storefront_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_id", "tenant_id", "storefront_id"],
            ["order.id", "order.tenant_id", "order.storefront_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "amount > 0 AND cost_byn_amount > 0", name="ck_worker_pay_agreement_amount"
        ),
        sa.CheckConstraint(
            "currency IN ('BYN','USD','EUR')", name="ck_worker_pay_agreement_currency"
        ),
        sa.CheckConstraint(
            "status IN ('agreed','accrued','cancelled')",
            name="ck_worker_pay_agreement_status",
        ),
        sa.CheckConstraint("version >= 0", name="ck_worker_pay_agreement_version"),
    )
    op.create_index(
        "uq_worker_pay_active_work",
        "worker_pay_agreement",
        ["account_id", "order_id", "work_key"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
        sqlite_where=sa.text("status <> 'cancelled'"),
    )
    op.create_table(
        "worker_pay_payout",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reversed_at", sa.DateTime(timezone=True)),
        sa.Column("reversal_reason", sa.String(500)),
        sa.UniqueConstraint("id", "account_id", name="uq_worker_pay_payout_account"),
        sa.ForeignKeyConstraint(
            ["account_id", "tenant_id", "storefront_id"],
            [
                "worker_cash_account.id",
                "worker_cash_account.tenant_id",
                "worker_cash_account.storefront_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount > 0", name="ck_worker_pay_payout_amount"),
        sa.CheckConstraint(
            "currency IN ('BYN','USD','EUR')", name="ck_worker_pay_payout_currency"
        ),
        sa.CheckConstraint(
            "method IN ('cash','bank','offset')", name="ck_worker_pay_payout_method"
        ),
        sa.CheckConstraint(
            "(reversed_at IS NULL AND reversal_reason IS NULL) OR (reversed_at IS NOT NULL AND reversal_reason IS NOT NULL)",
            name="ck_worker_pay_payout_reversal",
        ),
        sa.CheckConstraint("version >= 0", name="ck_worker_pay_payout_version"),
    )
    op.create_table(
        "worker_pay_payout_allocation",
        sa.Column("payout_id", sa.Integer(), primary_key=True),
        sa.Column("agreement_id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.ForeignKeyConstraint(
            ["payout_id", "account_id"],
            ["worker_pay_payout.id", "worker_pay_payout.account_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["agreement_id", "account_id"],
            ["worker_pay_agreement.id", "worker_pay_agreement.account_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount > 0", name="ck_worker_pay_payout_allocation_amount"),
    )
    op.create_table(
        "worker_pay_offset_cash_allocation",
        sa.Column("payout_id", sa.Integer(), primary_key=True),
        sa.Column("receipt_id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.ForeignKeyConstraint(
            ["payout_id", "account_id"],
            ["worker_pay_payout.id", "worker_pay_payout.account_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id", "account_id"],
            ["worker_cash_receipt.id", "worker_cash_receipt.account_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount > 0", name="ck_worker_pay_offset_cash_amount"),
    )
    for table, columns in {
        "worker_pay_agreement": ("account_id", "order_id"),
        "worker_pay_payout": ("account_id",),
        "worker_pay_payout_allocation": ("account_id",),
        "worker_pay_offset_cash_allocation": ("account_id",),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    raise RuntimeError(
        "Worker remuneration contains financial history; use a compatible application rollback"
    )
