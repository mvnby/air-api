"""add transactional outbox and communications delivery foundation

Revision ID: 3f7a9c1d2e04
Revises: 2d4f6a8b0c13
Create Date: 2026-07-13 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "3f7a9c1d2e04"
down_revision: Union[str, Sequence[str], None] = "2d4f6a8b0c13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration_outbox_event",
        sa.Column("event_id", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=True),
        sa.Column("deduplication_key", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("causation_id", sa.String(length=128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_token", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_message", sa.String(length=1000), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_outbox_attempts_non_negative"),
        sa.CheckConstraint("max_attempts > 0", name="ck_outbox_max_attempts_positive"),
        sa.CheckConstraint("schema_version > 0", name="ck_outbox_schema_version_positive"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'published', 'dead')",
            name="ck_outbox_status_valid",
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "deduplication_key",
            name="uq_integration_outbox_event_deduplication_key",
        ),
    )
    op.create_index(
        "ix_integration_outbox_event_aggregate",
        "integration_outbox_event",
        ["aggregate_type", "aggregate_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_integration_outbox_event_claim",
        "integration_outbox_event",
        ["status", "available_at", "priority", "occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_outbox_event_created_at"),
        "integration_outbox_event",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_outbox_event_event_type"),
        "integration_outbox_event",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_outbox_event_lease_expires_at"),
        "integration_outbox_event",
        ["lease_expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_outbox_event_published_at"),
        "integration_outbox_event",
        ["published_at"],
        unique=False,
    )

    op.create_table(
        "consumer_inbox",
        sa.Column("consumer_name", sa.String(length=120), nullable=False),
        sa.Column("event_id", sa.String(length=32), nullable=False),
        sa.Column("handler_version", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "handler_version > 0",
            name="ck_consumer_inbox_handler_version_positive",
        ),
        sa.PrimaryKeyConstraint("consumer_name", "event_id"),
    )
    op.create_index(
        "ix_consumer_inbox_processed_at",
        "consumer_inbox",
        ["processed_at"],
        unique=False,
    )

    op.create_table(
        "communication_delivery",
        sa.Column("delivery_id", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("recipient_key", sa.String(length=160), nullable=False),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column("template_key", sa.String(length=120), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("render_context", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_token", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("last_error_category", sa.String(length=80), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_message", sa.String(length=1000), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_delivery_attempts_non_negative"),
        sa.CheckConstraint("max_attempts > 0", name="ck_delivery_max_attempts_positive"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'retry', 'sent', 'dead', 'canceled')",
            name="ck_delivery_status_valid",
        ),
        sa.CheckConstraint(
            "template_version > 0",
            name="ck_delivery_template_version_positive",
        ),
        sa.PrimaryKeyConstraint("delivery_id"),
        sa.UniqueConstraint(
            "event_id",
            "channel",
            "recipient_key",
            "template_version",
            name="uq_communication_delivery_event_channel_recipient_template",
        ),
    )
    op.create_index(
        "ix_communication_delivery_claim",
        "communication_delivery",
        ["status", "available_at", "priority", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_communication_delivery_created_at"),
        "communication_delivery",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_communication_delivery_event_id",
        "communication_delivery",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_communication_delivery_lease_expires_at"),
        "communication_delivery",
        ["lease_expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_communication_delivery_sent_at"),
        "communication_delivery",
        ["sent_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_communication_delivery_sent_at"),
        table_name="communication_delivery",
    )
    op.drop_index(
        op.f("ix_communication_delivery_lease_expires_at"),
        table_name="communication_delivery",
    )
    op.drop_index("ix_communication_delivery_event_id", table_name="communication_delivery")
    op.drop_index(
        op.f("ix_communication_delivery_created_at"),
        table_name="communication_delivery",
    )
    op.drop_index("ix_communication_delivery_claim", table_name="communication_delivery")
    op.drop_table("communication_delivery")

    op.drop_index("ix_consumer_inbox_processed_at", table_name="consumer_inbox")
    op.drop_table("consumer_inbox")

    op.drop_index(
        op.f("ix_integration_outbox_event_published_at"),
        table_name="integration_outbox_event",
    )
    op.drop_index(
        op.f("ix_integration_outbox_event_lease_expires_at"),
        table_name="integration_outbox_event",
    )
    op.drop_index(
        op.f("ix_integration_outbox_event_event_type"),
        table_name="integration_outbox_event",
    )
    op.drop_index(
        op.f("ix_integration_outbox_event_created_at"),
        table_name="integration_outbox_event",
    )
    op.drop_index("ix_integration_outbox_event_claim", table_name="integration_outbox_event")
    op.drop_index("ix_integration_outbox_event_aggregate", table_name="integration_outbox_event")
    op.drop_table("integration_outbox_event")
