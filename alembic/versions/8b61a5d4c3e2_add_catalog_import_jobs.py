"""add catalog import jobs

Revision ID: 8b61a5d4c3e2
Revises: 7d2a1c9b4e11
Create Date: 2026-05-23 18:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b61a5d4c3e2"
down_revision: Union[str, Sequence[str], None] = "7d2a1c9b4e11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "catalog_import_job",
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(), nullable=False, server_default="queued"),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("input_urls", sa.JSON(), nullable=False),
        sa.Column("with_related", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("update_existing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("input_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("processed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("pending", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("current_url", sa.String(), nullable=True),
        sa.Column("current_title", sa.String(), nullable=True),
        sa.Column("successes", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index("ix_catalog_import_job_status", "catalog_import_job", ["status"], unique=False)
    op.create_index("ix_catalog_import_job_stage", "catalog_import_job", ["stage"], unique=False)
    op.create_index("ix_catalog_import_job_created_at", "catalog_import_job", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_catalog_import_job_created_at", table_name="catalog_import_job")
    op.drop_index("ix_catalog_import_job_stage", table_name="catalog_import_job")
    op.drop_index("ix_catalog_import_job_status", table_name="catalog_import_job")
    op.drop_table("catalog_import_job")
