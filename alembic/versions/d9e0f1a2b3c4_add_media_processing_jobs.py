"""add media processing jobs

Revision ID: d9e0f1a2b3c4
Revises: c2f8a4d6b901
Create Date: 2026-06-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "c2f8a4d6b901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_processing_jobs",
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("source_asset_id", sa.Integer(), nullable=False),
        sa.Column("result_asset_id", sa.Integer(), nullable=True),
        sa.Column("operation", sa.String(), nullable=False, server_default="background_removal"),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(), nullable=False, server_default="queued"),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("rembg_model", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("worker_id", sa.String(), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["result_asset_id"], ["media_asset.id"]),
        sa.ForeignKeyConstraint(["source_asset_id"], ["media_asset.id"]),
        sa.PrimaryKeyConstraint("job_id"),
    )
    for column in (
        "source_asset_id",
        "result_asset_id",
        "operation",
        "status",
        "stage",
        "provider",
        "rembg_model",
        "priority",
        "worker_id",
        "created_by",
        "created_at",
        "started_at",
        "lease_expires_at",
        "finished_at",
    ):
        op.create_index(f"ix_media_processing_jobs_{column}", "media_processing_jobs", [column], unique=False)


def downgrade() -> None:
    for column in (
        "finished_at",
        "lease_expires_at",
        "started_at",
        "created_at",
        "created_by",
        "worker_id",
        "priority",
        "rembg_model",
        "provider",
        "stage",
        "status",
        "operation",
        "result_asset_id",
        "source_asset_id",
    ):
        op.drop_index(f"ix_media_processing_jobs_{column}", table_name="media_processing_jobs")
    op.drop_table("media_processing_jobs")
