"""Personal incoming read state and reversible triage decisions.

Revision ID: fc2d3e4f5a6b
Revises: fb1c2d3e4f5a
"""

from alembic import op
import sqlalchemy as sa

revision = "fc2d3e4f5a6b"
down_revision = "fb1c2d3e4f5a"
branch_labels = None
depends_on = None


def _scope(prefix):
    return [
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["lead.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id", "tenant_id", "storefront_id"],
            ["order.id", "order.tenant_id", "order.storefront_id"], name=f"fk_inbox_{prefix}_order_scope", ondelete="CASCADE"),
        sa.CheckConstraint("(entity_kind = 'order' AND order_id IS NOT NULL AND order_id = entity_id AND lead_id IS NULL) OR "
            "(entity_kind = 'lead' AND lead_id IS NOT NULL AND lead_id = entity_id AND order_id IS NULL)",
            name=f"ck_inbox_{prefix}_identity"),
    ]


def _identity():
    return [sa.Column("entity_kind", sa.String(12), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer()), sa.Column("lead_id", sa.Integer()),
        sa.Column("tenant_id", sa.Integer(), nullable=False), sa.Column("storefront_id", sa.Integer(), nullable=False)]


def upgrade():
    op.create_table("inbox_read_state", *_identity(),
        sa.Column("username", sa.String(120), nullable=False), sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)), *_scope("read"),
        sa.PrimaryKeyConstraint("tenant_id", "username", "entity_kind", "entity_id"))
    op.create_table("inbox_triage_state", *_identity(),
        sa.Column("outcome", sa.String(32)), sa.Column("reason", sa.String(32)), sa.Column("note", sa.Text()),
        sa.Column("archived_at", sa.DateTime(timezone=True)), sa.Column("archived_by", sa.String(120)),
        sa.Column("restored_deadline_at", sa.DateTime(timezone=True)), *_scope("state"),
        sa.CheckConstraint("outcome IS NULL OR outcome IN ('refusal', 'spam', 'duplicate', 'deadline_expired')",
                           name="ck_inbox_state_outcome"), sa.PrimaryKeyConstraint("entity_kind", "entity_id"))
    op.create_index("ix_inbox_state_scope_archive", "inbox_triage_state", ["tenant_id", "storefront_id", "archived_at"])
    op.create_table("inbox_event", sa.Column("id", sa.Integer(), primary_key=True), *_identity(),
        sa.Column("kind", sa.String(24), nullable=False), sa.Column("actor", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("note", sa.Text()),
        sa.Column("outcome", sa.String(32)), sa.Column("reason", sa.String(32)),
        sa.Column("next_followup_at", sa.DateTime(timezone=True)), *_scope("event"))
    op.create_index("ix_inbox_event_entity_created", "inbox_event", ["entity_kind", "entity_id", "created_at", "id"])


def downgrade():
    op.drop_table("inbox_event")
    op.drop_table("inbox_triage_state")
    op.drop_table("inbox_read_state")
