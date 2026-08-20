"""add legacy owner authentication state

Revision ID: d2b3c4d5e6f7
Revises: d1a2b3c4e5f6
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "d1a2b3c4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "legacy_owner_auth_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "mode",
            sa.String(length=24),
            server_default="legacy",
            nullable=False,
        ),
        sa.Column(
            "legacy_token_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("owner_staff_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mode = 'legacy' OR owner_staff_user_id IS NOT NULL",
            name="ck_legacy_owner_auth_state_staff_mode_bound",
        ),
        sa.CheckConstraint(
            "mode IN ('legacy', 'staff_shadow', 'staff')",
            name="ck_legacy_owner_auth_state_mode_valid",
        ),
        sa.CheckConstraint(
            "id = 1",
            name="ck_legacy_owner_auth_state_singleton",
        ),
        sa.CheckConstraint(
            "legacy_token_version >= 1",
            name="ck_legacy_owner_auth_state_token_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["owner_staff_user_id"],
            ["staff_users.id"],
            name="fk_legacy_owner_auth_state_staff_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_staff_user_id",
            name="uq_legacy_owner_auth_state_staff_user",
        ),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO legacy_owner_auth_state (
                id, mode, legacy_token_version, owner_staff_user_id
            ) VALUES (1, 'legacy', 1, NULL)
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    row = connection.execute(
        sa.text(
            """
            SELECT mode, owner_staff_user_id
            FROM legacy_owner_auth_state
            WHERE id = 1
            """
        )
    ).mappings().one_or_none()
    if (
        row is None
        or row["mode"] != "legacy"
        or row["owner_staff_user_id"] is not None
    ):
        raise RuntimeError(
            "Refusing downgrade while legacy-owner cutover state is active"
        )
    op.drop_table("legacy_owner_auth_state")
