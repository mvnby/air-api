"""Add system-owned ZAPRO.SU AI credential.

Revision ID: e67a7b8c9d0f
Revises: e66a7b8c9d0e
"""

from alembic import op
import sqlalchemy as sa

revision = "e67a7b8c9d0f"
down_revision = "e66a7b8c9d0e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_ai_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column("credentials_fingerprint", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("selected_model", sa.String(160), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_platform_ai_connection_singleton"),
    )


def downgrade() -> None:
    op.drop_table("platform_ai_connection")
