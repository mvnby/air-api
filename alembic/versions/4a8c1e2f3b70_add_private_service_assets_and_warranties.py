"""add private service assets and equipment warranty coverage

Revision ID: 4a8c1e2f3b70
Revises: 6c0d3e5f7a21
Create Date: 2026-07-13 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "4a8c1e2f3b70"
down_revision: Union[str, Sequence[str], None] = "6c0d3e5f7a21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_attachment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_kind", sa.String(length=32), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("storage_provider", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
        sa.Column("preview_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("preview_mime_type", sa.String(length=160), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("source_meta", sa.JSON(), nullable=False),
        sa.Column("telegram_file_id", sa.String(length=255), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash", name="uq_service_attachment_content_hash"),
    )
    op.create_index("ix_service_attachment_created_at", "service_attachment", ["created_at"])
    op.create_index("ix_service_attachment_processing_status", "service_attachment", ["processing_status"])
    op.create_index("ix_service_attachment_telegram_file_id", "service_attachment", ["telegram_file_id"])
    op.create_index("ix_service_attachment_archived_at", "service_attachment", ["archived_at"])

    op.create_table(
        "order_attachment_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("attachment_id", sa.Integer(), nullable=False),
        sa.Column("work_stage_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["attachment_id"], ["service_attachment.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["order.id"]),
        sa.ForeignKeyConstraint(["work_stage_id"], ["order_work_stage.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "attachment_id", name="uq_order_attachment_link"),
    )
    op.create_index("ix_order_attachment_link_order_id", "order_attachment_link", ["order_id"])
    op.create_index("ix_order_attachment_link_attachment_id", "order_attachment_link", ["attachment_id"])
    op.create_index("ix_order_attachment_link_category", "order_attachment_link", ["category"])
    op.create_index("ix_order_attachment_link_archived_at", "order_attachment_link", ["archived_at"])

    op.create_table(
        "equipment_attachment_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("attachment_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("service_history_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["attachment_id"], ["service_attachment.id"]),
        sa.ForeignKeyConstraint(["component_id"], ["equipment_component.id"]),
        sa.ForeignKeyConstraint(["equipment_id"], ["customer_equipment.id"]),
        sa.ForeignKeyConstraint(["service_history_id"], ["equipment_service_history.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("equipment_id", "attachment_id", name="uq_equipment_attachment_link"),
    )
    op.create_index("ix_equipment_attachment_link_equipment_id", "equipment_attachment_link", ["equipment_id"])
    op.create_index("ix_equipment_attachment_link_attachment_id", "equipment_attachment_link", ["attachment_id"])
    op.create_index("ix_equipment_attachment_link_archived_at", "equipment_attachment_link", ["archived_at"])

    op.create_table(
        "equipment_order_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["equipment_id"], ["customer_equipment.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["order.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("equipment_id", "order_id", "role", name="uq_equipment_order_link_role"),
    )
    op.create_index("ix_equipment_order_link_equipment_id", "equipment_order_link", ["equipment_id"])
    op.create_index("ix_equipment_order_link_order_id", "equipment_order_link", ["order_id"])
    op.create_index("ix_equipment_order_link_role", "equipment_order_link", ["role"])

    op.create_table(
        "warranty_policy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("coverage_type", sa.String(length=32), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("brand_id", sa.Integer(), nullable=True),
        sa.Column("series_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("duration_months", sa.Integer(), nullable=True),
        sa.Column("start_event", sa.String(length=32), nullable=False),
        sa.Column("maintenance_required", sa.Boolean(), nullable=False),
        sa.Column("maintenance_interval_months", sa.Integer(), nullable=True),
        sa.Column("grace_period_days", sa.Integer(), nullable=False),
        sa.Column("allowed_maintenance_provider", sa.String(length=32), nullable=False),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column("effective_from", sa.DateTime(), nullable=True),
        sa.Column("effective_until", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brand.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["series_id"], ["product_series.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_warranty_policy_scope", "warranty_policy", ["product_id", "series_id", "brand_id", "supplier_id"])
    op.create_index("ix_warranty_policy_active", "warranty_policy", ["is_active", "effective_from", "effective_until"])

    op.create_table(
        "equipment_warranty_coverage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("policy_id", sa.Integer(), nullable=True),
        sa.Column("coverage_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("maintenance_required", sa.Boolean(), nullable=False),
        sa.Column("maintenance_interval_months", sa.Integer(), nullable=True),
        sa.Column("grace_period_days", sa.Integer(), nullable=False),
        sa.Column("allowed_maintenance_provider", sa.String(length=32), nullable=False),
        sa.Column("next_maintenance_due_at", sa.DateTime(), nullable=True),
        sa.Column("terms_snapshot", sa.Text(), nullable=True),
        sa.Column("policy_snapshot", sa.JSON(), nullable=False),
        sa.Column("decision_status", sa.String(length=32), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decided_by", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["equipment_component.id"]),
        sa.ForeignKeyConstraint(["equipment_id"], ["customer_equipment.id"]),
        sa.ForeignKeyConstraint(["policy_id"], ["warranty_policy.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("equipment_id", "component_id", "coverage_type", name="uq_equipment_warranty_scope"),
    )
    op.create_index("ix_equipment_warranty_coverage_equipment_id", "equipment_warranty_coverage", ["equipment_id"])
    op.create_index("ix_equipment_warranty_coverage_attention", "equipment_warranty_coverage", ["expires_at", "next_maintenance_due_at", "decision_status"])
    op.create_index(
        "uq_equipment_warranty_system_scope",
        "equipment_warranty_coverage",
        ["equipment_id", "coverage_type"],
        unique=True,
        postgresql_where=sa.text("component_id IS NULL"),
    )

    op.create_table(
        "equipment_warranty_decision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coverage_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["coverage_id"], ["equipment_warranty_coverage.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_equipment_warranty_decision_coverage_id", "equipment_warranty_decision", ["coverage_id"])

    op.create_table(
        "equipment_maintenance_reminder",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("coverage_id", sa.Integer(), nullable=False),
        sa.Column("reminder_type", sa.String(length=32), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["coverage_id"], ["equipment_warranty_coverage.id"]),
        sa.ForeignKeyConstraint(["equipment_id"], ["customer_equipment.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "coverage_id",
            "reminder_type",
            "due_at",
            name="uq_equipment_maintenance_reminder_cycle",
        ),
    )
    op.create_index(
        "ix_equipment_maintenance_reminder_equipment_id",
        "equipment_maintenance_reminder",
        ["equipment_id"],
    )
    op.create_index(
        "ix_equipment_maintenance_reminder_status",
        "equipment_maintenance_reminder",
        ["status", "due_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_equipment_maintenance_reminder_status", table_name="equipment_maintenance_reminder")
    op.drop_index("ix_equipment_maintenance_reminder_equipment_id", table_name="equipment_maintenance_reminder")
    op.drop_table("equipment_maintenance_reminder")
    op.drop_index("ix_equipment_warranty_decision_coverage_id", table_name="equipment_warranty_decision")
    op.drop_table("equipment_warranty_decision")
    op.drop_index("ix_equipment_warranty_coverage_attention", table_name="equipment_warranty_coverage")
    op.drop_index("uq_equipment_warranty_system_scope", table_name="equipment_warranty_coverage")
    op.drop_index("ix_equipment_warranty_coverage_equipment_id", table_name="equipment_warranty_coverage")
    op.drop_table("equipment_warranty_coverage")
    op.drop_index("ix_warranty_policy_active", table_name="warranty_policy")
    op.drop_index("ix_warranty_policy_scope", table_name="warranty_policy")
    op.drop_table("warranty_policy")
    op.drop_index("ix_equipment_order_link_role", table_name="equipment_order_link")
    op.drop_index("ix_equipment_order_link_order_id", table_name="equipment_order_link")
    op.drop_index("ix_equipment_order_link_equipment_id", table_name="equipment_order_link")
    op.drop_table("equipment_order_link")
    op.drop_index("ix_equipment_attachment_link_attachment_id", table_name="equipment_attachment_link")
    op.drop_index("ix_equipment_attachment_link_archived_at", table_name="equipment_attachment_link")
    op.drop_index("ix_equipment_attachment_link_equipment_id", table_name="equipment_attachment_link")
    op.drop_table("equipment_attachment_link")
    op.drop_index("ix_order_attachment_link_category", table_name="order_attachment_link")
    op.drop_index("ix_order_attachment_link_archived_at", table_name="order_attachment_link")
    op.drop_index("ix_order_attachment_link_attachment_id", table_name="order_attachment_link")
    op.drop_index("ix_order_attachment_link_order_id", table_name="order_attachment_link")
    op.drop_table("order_attachment_link")
    op.drop_index("ix_service_attachment_archived_at", table_name="service_attachment")
    op.drop_index("ix_service_attachment_telegram_file_id", table_name="service_attachment")
    op.drop_index("ix_service_attachment_processing_status", table_name="service_attachment")
    op.drop_index("ix_service_attachment_created_at", table_name="service_attachment")
    op.drop_table("service_attachment")
