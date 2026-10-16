"""Browser-bound single-use Telegram proofs.

Revision ID: t1162telegram01
Revises: t1162profile01
"""

from alembic import op
import sqlalchemy as sa

revision = "t1162telegram01"
down_revision = "t1162profile01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "staff_telegram_challenge",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("staff_user_id", sa.Integer(), sa.ForeignKey("staff_users.id"), nullable=True),
        sa.Column("auth_version", sa.Integer(), nullable=True),
        sa.Column("previous_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_username", sa.String(160), nullable=True),
        sa.Column("telegram_display_name", sa.String(300), nullable=True),
        sa.Column("browser_code", sa.String(8), nullable=True),
        sa.Column("claim_key", sa.String(100), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_staff_telegram_challenge_purpose", "staff_telegram_challenge", ["purpose"])
    op.create_index("ix_staff_telegram_challenge_staff_user_id", "staff_telegram_challenge", ["staff_user_id"])
    op.create_table("staff_telegram_widget_receipt",
                    sa.Column("signature_hash", sa.String(64), primary_key=True),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("staff_telegram_retired_identity",
                    sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
                    sa.Column("staff_user_id", sa.Integer(), sa.ForeignKey("staff_users.id"), nullable=False),
                    sa.Column("retired_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_staff_telegram_retired_identity_staff_user_id", "staff_telegram_retired_identity", ["staff_user_id"])


def downgrade():
    op.drop_table("staff_telegram_retired_identity")
    op.drop_table("staff_telegram_widget_receipt")
    op.drop_table("staff_telegram_challenge")
