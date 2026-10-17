"""Worker client receipts and accountable cash custody, without historical backfills."""

from alembic import op
import sqlalchemy as sa

revision = "w20261017cash01"
down_revision = "t1167worker02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_payment_id_order", "payment", ["id", "order_id"])
    op.create_table(
        "worker_cash_account",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("worker_profile_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "worker_profile_id", "storefront_id", name="uq_worker_cash_profile_site"
        ),
        sa.UniqueConstraint(
            "id", "tenant_id", "storefront_id", name="uq_worker_cash_account_scope"
        ),
        sa.ForeignKeyConstraint(
            ["worker_profile_id", "tenant_id"],
            ["tenant_worker_profile.id", "tenant_worker_profile.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("version >= 0", name="ck_worker_cash_account_version"),
    )
    op.create_table(
        "worker_cash_receipt",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("assignment_reference", sa.Integer(), nullable=False),
        sa.Column("collection_version", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reversal_payment_id", sa.Integer(), unique=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True)),
        sa.Column("reversal_reason", sa.String(500)),
        sa.UniqueConstraint("id", "account_id", name="uq_worker_cash_receipt_account"),
        sa.UniqueConstraint(
            "order_id", "collection_version", name="uq_worker_cash_receipt_instruction"
        ),
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
        sa.ForeignKeyConstraint(
            ["payment_id", "order_id"],
            ["payment.id", "payment.order_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reversal_payment_id", "order_id"],
            ["payment.id", "payment.order_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount > 0", name="ck_worker_cash_receipt_amount"),
        sa.CheckConstraint(
            "collection_version >= 0", name="ck_worker_cash_receipt_version"
        ),
        sa.CheckConstraint(
            "currency IN ('BYN','USD','EUR')", name="ck_worker_cash_receipt_currency"
        ),
        sa.CheckConstraint(
            "(reversal_payment_id IS NULL AND reversed_at IS NULL AND reversal_reason IS NULL) OR (reversal_payment_id IS NOT NULL AND reversed_at IS NOT NULL AND reversal_reason IS NOT NULL)",
            name="ck_worker_cash_receipt_reversal",
        ),
    )
    op.create_table(
        "worker_cash_handover",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("recipient_staff_user_id", sa.Integer(), nullable=False),
        sa.Column("recipient_name", sa.String(160), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("id", "account_id", name="uq_worker_cash_handover_account"),
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
            ["tenant_id", "recipient_staff_user_id"],
            ["tenant_membership.tenant_id", "tenant_membership.staff_user_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount > 0", name="ck_worker_cash_handover_amount"),
        sa.CheckConstraint(
            "currency IN ('BYN','USD','EUR')", name="ck_worker_cash_handover_currency"
        ),
        sa.CheckConstraint(
            "status IN ('pending','confirmed','rejected','cancelled')",
            name="ck_worker_cash_handover_status",
        ),
        sa.CheckConstraint("version >= 0", name="ck_worker_cash_handover_version"),
        sa.CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL) OR (status <> 'pending' AND resolved_at IS NOT NULL)",
            name="ck_worker_cash_handover_resolution",
        ),
    )
    op.create_table(
        "worker_cash_handover_allocation",
        sa.Column("handover_id", sa.Integer(), primary_key=True),
        sa.Column("receipt_id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.ForeignKeyConstraint(
            ["handover_id", "account_id"],
            ["worker_cash_handover.id", "worker_cash_handover.account_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id", "account_id"],
            ["worker_cash_receipt.id", "worker_cash_receipt.account_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "amount > 0", name="ck_worker_cash_handover_allocation_amount"
        ),
    )
    op.create_table(
        "worker_money_command",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("worker_cash_account.id"),
            nullable=False,
        ),
        sa.Column(
            "actor_staff_user_id",
            sa.Integer(),
            sa.ForeignKey("staff_users.id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "account_id", "idempotency_key", name="uq_worker_money_command_key"
        ),
    )
    for table, columns in {
        "worker_cash_account": ("tenant_id", "storefront_id", "worker_profile_id"),
        "worker_cash_receipt": ("account_id", "order_id"),
        "worker_cash_handover": ("account_id",),
        "worker_cash_handover_allocation": ("account_id",),
        "worker_money_command": ("account_id",),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    # Never discard accountable cash records through an automated rollback.
    raise RuntimeError(
        "Worker cash schema contains financial history; use a compatible application rollback"
    )
