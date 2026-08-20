"""add durable password-login throttle

Revision ID: d1a2b3c4e5f6
Revises: c8d9e0f1a2b3
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "d1a2b3c4e5f6"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_login_throttle",
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "failure_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(fingerprint) = 64",
            name="ck_auth_login_throttle_fingerprint_length",
        ),
        sa.CheckConstraint(
            "failure_count >= 0",
            name="ck_auth_login_throttle_failure_count_nonnegative",
        ),
        sa.PrimaryKeyConstraint("fingerprint"),
    )
    op.create_index(
        "ix_auth_login_throttle_updated_at",
        "auth_login_throttle",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auth_login_throttle_updated_at",
        table_name="auth_login_throttle",
    )
    op.drop_table("auth_login_throttle")
