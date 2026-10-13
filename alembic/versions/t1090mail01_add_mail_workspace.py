"""Extend outgoing history with drafts, private snapshots and standalone inbox.

Revision ID: t1090mail01
Revises: t1089scan02
"""

from alembic import op
import sqlalchemy as sa

revision = "t1090mail01"
down_revision = "t1089scan02"
branch_labels = None
depends_on = None


def upgrade():
    columns = [
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("storefront_id", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.String(64), nullable=False, server_default="system"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cc_emails", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("bcc_emails", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_by_staff_user_id", sa.Integer(), nullable=True),
        sa.Column("sent_by_staff_user_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_version", sa.Integer(), nullable=True),
        sa.Column("confirmed_hash", sa.String(), nullable=True),
        sa.Column("confirmed_by_staff_user_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("send_started_at", sa.DateTime(), nullable=True),
        sa.Column("send_token", sa.String(), nullable=True),
    ]
    for column in columns:
        op.add_column("outgoing_email", column)
    for column, table in (("tenant_id", "tenant"), ("storefront_id", "storefront"),
        ("created_by_staff_user_id", "staff_users"), ("sent_by_staff_user_id", "staff_users"),
        ("confirmed_by_staff_user_id", "staff_users")):
        op.create_foreign_key(f"fk_outgoing_email_{column}", "outgoing_email", table, [column], ["id"])
    op.create_index("ix_outgoing_email_tenant_id", "outgoing_email", ["tenant_id"])
    op.create_index("ix_outgoing_email_storefront_id", "outgoing_email", ["storefront_id"])
    op.create_table("mail_attachment_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("email_id", sa.Integer(), sa.ForeignKey("outgoing_email.id"), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
    )
    for column in ("email_id", "tenant_id"):
        op.create_index(f"ix_mail_attachment_snapshot_{column}", "mail_attachment_snapshot", [column])
    op.create_table("incoming_mail",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("sender_email", sa.String(), nullable=False),
        sa.Column("sender_name", sa.String(), nullable=False),
        sa.Column("recipient_email", sa.String(), nullable=False),
        sa.Column("cc_emails", sa.JSON(), nullable=True),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body_text", sa.String(), nullable=False),
        sa.Column("body_html", sa.String(), nullable=True),
        sa.Column("attachments", sa.JSON(), nullable=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("order.id"), nullable=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id"), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "account_id", "source_key", name="uq_incoming_mail_source"),
    )
    for column in ("tenant_id", "source_key", "order_id", "customer_id", "received_at"):
        op.create_index(f"ix_incoming_mail_{column}", "incoming_mail", [column])
    op.create_table("incoming_mail_attachment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("email_id", sa.Integer(), sa.ForeignKey("incoming_mail.id"), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
    )
    for column in ("email_id", "tenant_id"):
        op.create_index(f"ix_incoming_mail_attachment_{column}", "incoming_mail_attachment", [column])


def downgrade():
    op.drop_table("incoming_mail_attachment")
    op.drop_table("incoming_mail")
    op.drop_table("mail_attachment_snapshot")
    op.drop_index("ix_outgoing_email_storefront_id", table_name="outgoing_email")
    op.drop_index("ix_outgoing_email_tenant_id", table_name="outgoing_email")
    for column in ("tenant_id", "storefront_id", "created_by_staff_user_id", "sent_by_staff_user_id", "confirmed_by_staff_user_id"):
        op.drop_constraint(f"fk_outgoing_email_{column}", "outgoing_email", type_="foreignkey")
    for column in ("tenant_id", "storefront_id", "account_id", "version", "cc_emails", "bcc_emails",
        "created_by_staff_user_id", "sent_by_staff_user_id", "confirmed_version", "confirmed_hash",
        "confirmed_by_staff_user_id", "confirmed_at", "send_started_at", "send_token"):
        op.drop_column("outgoing_email", column)
