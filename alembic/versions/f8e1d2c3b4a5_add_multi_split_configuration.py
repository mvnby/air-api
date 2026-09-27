"""Add persisted compatibility profiles and multi-split configurations.

Revision ID: f8e1d2c3b4a5
Revises: e71f4a6b8c02
"""

import sqlalchemy as sa
from alembic import op


revision = "f8e1d2c3b4a5"
down_revision = "e71f4a6b8c02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "multi_split_compatibility_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("outdoor_product_id", sa.Integer(), sa.ForeignKey("product.id"), nullable=False),
        sa.Column(
            "verification_status",
            sa.String(length=24),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_version", sa.String(length=255), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("verified_by", sa.String(length=120), nullable=True),
        sa.Column("max_indoor_units", sa.Integer(), nullable=True),
        sa.Column("allowed_indoor_product_ids", sa.JSON(), nullable=False),
        sa.Column("exact_combinations", sa.JSON(), nullable=False),
        sa.Column("mandatory_component_product_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "outdoor_product_id",
            name="uq_multi_split_compatibility_profile_outdoor_product",
        ),
        sa.CheckConstraint(
            "verification_status IN ('draft', 'verified')",
            name="ck_multi_split_compatibility_profile_verification_status",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_multi_split_compatibility_profile_version_positive",
        ),
        sa.CheckConstraint(
            "max_indoor_units IS NULL OR max_indoor_units > 0",
            name="ck_multi_split_compatibility_profile_max_indoor_units_positive",
        ),
    )
    op.create_index(
        "ix_multi_split_compatibility_profile_outdoor_product_id",
        "multi_split_compatibility_profile",
        ["outdoor_product_id"],
    )
    op.create_index(
        "ix_multi_split_compatibility_profile_verification_status",
        "multi_split_compatibility_profile",
        ["verification_status"],
    )
    op.create_index(
        "ix_multi_split_compatibility_profile_verified_at",
        "multi_split_compatibility_profile",
        ["verified_at"],
    )

    op.create_table(
        "order_multi_split_configuration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("order.id"), nullable=False),
        sa.Column("proposal_id", sa.Integer(), sa.ForeignKey("order_proposal.id"), nullable=False),
        sa.Column("rooms", sa.JSON(), nullable=False),
        sa.Column("component_snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "verification_status",
            sa.String(length=32),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("multi_split_compatibility_profile.id"),
            nullable=True,
        ),
        sa.Column("profile_version", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_version", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "proposal_id",
            name="uq_order_multi_split_configuration_proposal",
        ),
        sa.CheckConstraint(
            "verification_status IN ('draft', 'confirmed', 'requires_specialist', 'incompatible')",
            name="ck_order_multi_split_configuration_verification_status",
        ),
    )
    op.create_index(
        "ix_order_multi_split_configuration_order_id",
        "order_multi_split_configuration",
        ["order_id"],
    )
    op.create_index(
        "ix_order_multi_split_configuration_proposal_id",
        "order_multi_split_configuration",
        ["proposal_id"],
    )
    op.create_index(
        "ix_order_multi_split_configuration_profile_id",
        "order_multi_split_configuration",
        ["profile_id"],
    )
    op.create_index(
        "ix_order_multi_split_configuration_verification_status",
        "order_multi_split_configuration",
        ["verification_status"],
    )

    op.create_table(
        "lead_multi_split_configuration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("lead.id"), nullable=False),
        sa.Column("rooms", sa.JSON(), nullable=False),
        sa.Column("component_snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "verification_status",
            sa.String(length=32),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("multi_split_compatibility_profile.id"),
            nullable=True,
        ),
        sa.Column("profile_version", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_version", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("lead_id", name="uq_lead_multi_split_configuration_lead"),
        sa.CheckConstraint(
            "verification_status IN ('draft', 'confirmed', 'requires_specialist', 'incompatible')",
            name="ck_lead_multi_split_configuration_verification_status",
        ),
    )
    op.create_index(
        "ix_lead_multi_split_configuration_lead_id",
        "lead_multi_split_configuration",
        ["lead_id"],
    )
    op.create_index(
        "ix_lead_multi_split_configuration_profile_id",
        "lead_multi_split_configuration",
        ["profile_id"],
    )
    op.create_index(
        "ix_lead_multi_split_configuration_verification_status",
        "lead_multi_split_configuration",
        ["verification_status"],
    )


def downgrade() -> None:
    op.drop_table("lead_multi_split_configuration")
    op.drop_table("order_multi_split_configuration")
    op.drop_table("multi_split_compatibility_profile")
