"""Create disabled Jev connection and durable shadow samples. No keys or backfill."""
from alembic import op
import sqlalchemy as sa

revision = "fe34cd56ef78"
down_revision = "fe23bc45de67"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("jev_connection",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("encrypted_credentials", sa.Text(), nullable=True),
        sa.Column("credentials_fingerprint", sa.String(64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("daily_budget_usd", sa.Numeric(12, 8), nullable=False),
        sa.Column("budget_day", sa.Date(), nullable=True),
        sa.Column("budget_used_usd", sa.Numeric(12, 8), nullable=False),
        sa.Column("daily_requests", sa.Integer(), nullable=False),
        sa.CheckConstraint('daily_budget_usd > 0 AND daily_budget_usd <= 5', name="ck_jev_connection_budget"),
        sa.CheckConstraint('NOT enabled OR encrypted_credentials IS NOT NULL', name="ck_jev_connection_enabled_key"),
        sa.CheckConstraint('(encrypted_credentials IS NULL) = (credentials_fingerprint IS NULL)', name="ck_jev_connection_key_pair"),
        sa.CheckConstraint('id = 1', name="ck_jev_connection_singleton"),
    )
    op.create_table("jev_shadow_sample",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("sample_key", sa.String(64), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("budget_day", sa.Date(), nullable=True),
        sa.Column("primary_provider", sa.String(32), nullable=False),
        sa.Column("primary_model_requested", sa.String(160), nullable=True),
        sa.Column("primary_is_relevant", sa.Boolean(), nullable=True),
        sa.Column("primary_duration_ms", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("kind", sa.String(32), nullable=True),
        sa.Column("kind_confidence", sa.Float(), nullable=True),
        sa.Column("hvac_probability", sa.Float(), nullable=True),
        sa.Column("jev_is_relevant", sa.Boolean(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("estimated_usd", sa.Numeric(12, 8), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.CheckConstraint("source IN ('email', 'belzakupki')", name="ck_jev_shadow_source"),
        sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="ck_jev_shadow_status"),
        sa.ForeignKeyConstraint(['storefront_id', 'tenant_id'], ['storefront.id', 'storefront.tenant_id'], name="fk_jev_shadow_scope"),
        sa.UniqueConstraint('tenant_id', 'storefront_id', 'source', 'sample_key', name="uq_jev_shadow_sample"),
    )
    op.create_index("ix_jev_shadow_sample_created_at", "jev_shadow_sample", ['created_at'])
    op.create_index("ix_jev_shadow_sample_status", "jev_shadow_sample", ['status'])
    op.create_index("ix_jev_shadow_sample_tenant_id", "jev_shadow_sample", ['tenant_id'])


def downgrade() -> None:
    op.drop_table("jev_shadow_sample")
    op.drop_table("jev_connection")
