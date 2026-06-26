"""add bot fsm state table

Revision ID: 0abf9e6d4c12
Revises: f5a6b7c8d9e0
Create Date: 2026-06-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision: str = "0abf9e6d4c12"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if index_name not in _index_names(table_name):
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    if not _table_exists("bot_fsm_state"):
        op.create_table(
            "bot_fsm_state",
            sa.Column("storage_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("bot_id", sa.Integer(), nullable=False),
            sa.Column("chat_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("thread_id", sa.Integer(), nullable=True),
            sa.Column("business_connection_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("destiny", sa.String(), nullable=False),
            sa.Column("state", sa.String(), nullable=True),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("storage_key"),
        )
    _create_index_if_missing(op.f("ix_bot_fsm_state_bot_id"), "bot_fsm_state", ["bot_id"])
    _create_index_if_missing(op.f("ix_bot_fsm_state_chat_id"), "bot_fsm_state", ["chat_id"])
    _create_index_if_missing(op.f("ix_bot_fsm_state_user_id"), "bot_fsm_state", ["user_id"])
    _create_index_if_missing(op.f("ix_bot_fsm_state_thread_id"), "bot_fsm_state", ["thread_id"])
    _create_index_if_missing(op.f("ix_bot_fsm_state_business_connection_id"), "bot_fsm_state", ["business_connection_id"])
    _create_index_if_missing(op.f("ix_bot_fsm_state_destiny"), "bot_fsm_state", ["destiny"])
    _create_index_if_missing(op.f("ix_bot_fsm_state_updated_at"), "bot_fsm_state", ["updated_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_bot_fsm_state_updated_at"), table_name="bot_fsm_state")
    op.drop_index(op.f("ix_bot_fsm_state_destiny"), table_name="bot_fsm_state")
    op.drop_index(op.f("ix_bot_fsm_state_business_connection_id"), table_name="bot_fsm_state")
    op.drop_index(op.f("ix_bot_fsm_state_thread_id"), table_name="bot_fsm_state")
    op.drop_index(op.f("ix_bot_fsm_state_user_id"), table_name="bot_fsm_state")
    op.drop_index(op.f("ix_bot_fsm_state_chat_id"), table_name="bot_fsm_state")
    op.drop_index(op.f("ix_bot_fsm_state_bot_id"), table_name="bot_fsm_state")
    op.drop_table("bot_fsm_state")
