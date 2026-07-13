"""harden service assets and maintenance history

Revision ID: 5b9d7e1a2c80
Revises: 4a8c1e2f3b70
Create Date: 2026-07-13 18:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "5b9d7e1a2c80"
down_revision: Union[str, Sequence[str], None] = "4a8c1e2f3b70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_service_attachment_content_hash",
        "service_attachment",
        type_="unique",
    )
    op.create_index(
        "ix_service_attachment_content_hash",
        "service_attachment",
        ["content_hash"],
    )

    op.add_column(
        "equipment_attachment_link",
        sa.Column("order_attachment_link_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_equipment_attachment_link_order_attachment_link",
        "equipment_attachment_link",
        "order_attachment_link",
        ["order_attachment_link_id"],
        ["id"],
    )
    op.create_index(
        "ix_equipment_attachment_link_order_attachment_link_id",
        "equipment_attachment_link",
        ["order_attachment_link_id"],
    )

    op.add_column(
        "equipment_service_history",
        sa.Column("maintenance_provider", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_equipment_service_history_maintenance_provider",
        "equipment_service_history",
        ["maintenance_provider"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_equipment_service_history_maintenance_provider",
        table_name="equipment_service_history",
    )
    op.drop_column("equipment_service_history", "maintenance_provider")

    op.drop_index(
        "ix_equipment_attachment_link_order_attachment_link_id",
        table_name="equipment_attachment_link",
    )
    op.drop_constraint(
        "fk_equipment_attachment_link_order_attachment_link",
        "equipment_attachment_link",
        type_="foreignkey",
    )
    op.drop_column("equipment_attachment_link", "order_attachment_link_id")

    op.drop_index("ix_service_attachment_content_hash", table_name="service_attachment")
    op.create_unique_constraint(
        "uq_service_attachment_content_hash",
        "service_attachment",
        ["content_hash"],
    )
