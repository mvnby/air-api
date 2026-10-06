"""Add authenticated connector, persistent incoming requests and personal tasks.

Revision ID: f10a2b3c4d5e
Revises: fe34cd56ef78
"""

from alembic import op
import sqlalchemy as sa

revision = "f10a2b3c4d5e"
down_revision = "fe34cd56ef78"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("lead", sa.Column("intake_event_key", sa.String(), nullable=True))
    op.add_column("lead", sa.Column("intake_meta", sa.JSON(), nullable=True))
    op.add_column(
        "lead", sa.Column("version", sa.Integer(), server_default="1", nullable=False)
    )
    op.create_index(
        op.f("ix_lead_intake_event_key"), "lead", ["intake_event_key"], unique=True
    )
    op.create_table(
        "command_audit_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("staff_user_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_command_audit_scope_created",
        "command_audit_event",
        ["tenant_id", "storefront_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "connector_consent",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("staff_user_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("session_hash", sa.String(), nullable=False),
        sa.Column("csrf_hash", sa.String(), nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("redirect_uri", sa.String(), nullable=False),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("code_challenge", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["tenant_membership.id"],
        ),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_connector_consent_storefront_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["storefront_id"],
            ["storefront.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "connector_grant",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("staff_user_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["tenant_membership.id"],
        ),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_connector_grant_storefront_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["storefront_id"],
            ["storefront.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_connector_grant_staff_user_id"),
        "connector_grant",
        ["staff_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_grant_tenant_id"),
        "connector_grant",
        ["tenant_id"],
        unique=False,
    )
    op.create_table(
        "connector_auth_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("grant_id", sa.Integer(), nullable=False),
        sa.Column("staff_user_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["grant_id"],
            ["connector_grant.id"],
        ),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_connector_auth_event_grant_id"),
        "connector_auth_event",
        ["grant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_auth_event_staff_user_id"),
        "connector_auth_event",
        ["staff_user_id"],
        unique=False,
    )
    op.create_table(
        "connector_authorization_code",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("grant_id", sa.Integer(), nullable=False),
        sa.Column("redirect_uri", sa.String(), nullable=False),
        sa.Column("code_challenge", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["grant_id"],
            ["connector_grant.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_connector_authorization_code_code_hash"),
        "connector_authorization_code",
        ["code_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_connector_authorization_code_grant_id"),
        "connector_authorization_code",
        ["grant_id"],
        unique=False,
    )
    op.create_table(
        "connector_token",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("grant_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["grant_id"],
            ["connector_grant.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_connector_token_grant_id"),
        "connector_token",
        ["grant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_token_token_hash"),
        "connector_token",
        ["token_hash"],
        unique=True,
    )
    op.create_table(
        "personal_task",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("author_staff_user_id", sa.Integer(), nullable=False),
        sa.Column("assignee_staff_user_id", sa.Integer(), nullable=True),
        sa.Column("text", sa.String(length=2000), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lead_id", sa.Integer(), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("equipment_id", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_personal_task_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_personal_task_version_positive"),
        sa.ForeignKeyConstraint(
            ["assignee_staff_user_id"],
            ["staff_users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["author_staff_user_id"],
            ["staff_users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customer.id"],
        ),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["customer_equipment.id"],
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["lead.id"],
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["order.id"],
        ),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_personal_task_storefront_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_personal_task_assignee_staff_user_id"),
        "personal_task",
        ["assignee_staff_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_personal_task_author_staff_user_id"),
        "personal_task",
        ["author_staff_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_personal_task_customer_id"),
        "personal_task",
        ["customer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_personal_task_equipment_id"),
        "personal_task",
        ["equipment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_personal_task_lead_id"), "personal_task", ["lead_id"], unique=False
    )
    op.create_index(
        op.f("ix_personal_task_order_id"), "personal_task", ["order_id"], unique=False
    )
    op.create_index(
        "ix_personal_task_scope_assignee_status",
        "personal_task",
        ["tenant_id", "storefront_id", "assignee_staff_user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_personal_task_scope_author_status",
        "personal_task",
        ["tenant_id", "storefront_id", "author_staff_user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_personal_task_scope_reminder",
        "personal_task",
        ["tenant_id", "storefront_id", "status", "reminder_at"],
        unique=False,
    )
    op.create_index(
        "ix_personal_task_scope_status_due",
        "personal_task",
        ["tenant_id", "storefront_id", "status", "due_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_personal_task_scope_status_due", table_name="personal_task")
    op.drop_index("ix_personal_task_scope_reminder", table_name="personal_task")
    op.drop_index("ix_personal_task_scope_author_status", table_name="personal_task")
    op.drop_index("ix_personal_task_scope_assignee_status", table_name="personal_task")
    op.drop_index(op.f("ix_personal_task_order_id"), table_name="personal_task")
    op.drop_index(op.f("ix_personal_task_lead_id"), table_name="personal_task")
    op.drop_index(op.f("ix_personal_task_equipment_id"), table_name="personal_task")
    op.drop_index(op.f("ix_personal_task_customer_id"), table_name="personal_task")
    op.drop_index(
        op.f("ix_personal_task_author_staff_user_id"), table_name="personal_task"
    )
    op.drop_index(
        op.f("ix_personal_task_assignee_staff_user_id"), table_name="personal_task"
    )
    op.drop_table("personal_task")
    op.drop_index(op.f("ix_connector_token_token_hash"), table_name="connector_token")
    op.drop_index(op.f("ix_connector_token_grant_id"), table_name="connector_token")
    op.drop_table("connector_token")
    op.drop_index(
        op.f("ix_connector_authorization_code_grant_id"),
        table_name="connector_authorization_code",
    )
    op.drop_index(
        op.f("ix_connector_authorization_code_code_hash"),
        table_name="connector_authorization_code",
    )
    op.drop_table("connector_authorization_code")
    op.drop_index(
        op.f("ix_connector_auth_event_staff_user_id"), table_name="connector_auth_event"
    )
    op.drop_index(
        op.f("ix_connector_auth_event_grant_id"), table_name="connector_auth_event"
    )
    op.drop_table("connector_auth_event")
    op.drop_index(op.f("ix_connector_grant_tenant_id"), table_name="connector_grant")
    op.drop_index(
        op.f("ix_connector_grant_staff_user_id"), table_name="connector_grant"
    )
    op.drop_table("connector_grant")
    op.drop_table("connector_consent")
    op.drop_index("ix_command_audit_scope_created", table_name="command_audit_event")
    op.drop_table("command_audit_event")
    op.drop_index(op.f("ix_lead_intake_event_key"), table_name="lead")
    op.drop_column("lead", "version")
    op.drop_column("lead", "intake_meta")
    op.drop_column("lead", "intake_event_key")
