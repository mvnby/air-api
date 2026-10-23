"""Persist bounded mailbox progress, reply headers and delivery obligations.

Revision ID: mail20261023rel01
Revises: dash20261023snap01
"""
from alembic import op
import sqlalchemy as sa

revision = "mail20261023rel01"
down_revision = "dash20261023snap01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("mail_sync_cursor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("folder", sa.String(512), nullable=False),
        sa.Column("uidvalidity", sa.String(64), nullable=False),
        sa.Column("last_uid", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("tenant_id", "account_id", "folder", name="uq_mail_sync_cursor_scope"))
    op.add_column("incoming_mail", sa.Column("reply_to", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    for table in ("incoming_mail", "outgoing_email"):
        op.add_column(table, sa.Column("in_reply_to", sa.String(), nullable=True))
        op.add_column(table, sa.Column("references", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    # Existing history is immutable and does not acquire retrospective delivery work.
    op.add_column("outgoing_email", sa.Column("delivery_projection_pending", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("outgoing_email", "delivery_projection_pending")
    for table in ("outgoing_email", "incoming_mail"):
        op.drop_column(table, "references")
        op.drop_column(table, "in_reply_to")
    op.drop_column("incoming_mail", "reply_to")
    op.drop_table("mail_sync_cursor")
