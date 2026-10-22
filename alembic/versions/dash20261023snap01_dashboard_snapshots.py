"""Durable dashboard source snapshots and stable configuration revision; no backfill."""
from alembic import op
import sqlalchemy as sa

revision = "dash20261023snap01"
down_revision = "kan20261022wait01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("analytics_connection", sa.Column("snapshot_revision", sa.String(64), nullable=False, server_default="initial"))
    op.create_table("dashboard_analytics_snapshot",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(48), nullable=False),
        sa.Column("configuration_revision", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(32)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["storefront_id", "tenant_id"], ["storefront.id", "storefront.tenant_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_dashboard_snapshot_scope_source", "dashboard_analytics_snapshot",
                    ["tenant_id", "storefront_id", "provider", "configuration_revision", "period_start", "period_end"])


def downgrade():
    op.drop_index("ix_dashboard_snapshot_scope_source", table_name="dashboard_analytics_snapshot")
    op.drop_table("dashboard_analytics_snapshot")
    op.drop_column("analytics_connection", "snapshot_revision")
