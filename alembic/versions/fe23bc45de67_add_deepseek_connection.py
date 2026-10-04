"""Add system-owned DeepSeek settings without copying environment secrets.

Revision ID: fe23bc45de67
Revises: fe12ab34cd56
"""

from alembic import op
import sqlalchemy as sa

revision = "fe23bc45de67"
down_revision = "fe12ab34cd56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepseek_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("encrypted_credentials", sa.Text(), nullable=True),
        sa.Column("credentials_fingerprint", sa.String(64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_deepseek_connection_singleton"),
        sa.CheckConstraint(
            "(encrypted_credentials IS NULL) = (credentials_fingerprint IS NULL)",
            name="ck_deepseek_connection_credential_pair",
        ),
        sa.CheckConstraint("NOT enabled OR encrypted_credentials IS NOT NULL", name="ck_deepseek_connection_enabled_key"),
    )


def downgrade() -> None:
    op.drop_table("deepseek_connection")
