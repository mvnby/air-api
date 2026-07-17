"""add Telegram bot idempotency indexes

Revision ID: 7f2b4d6e8a10
Revises: 6e1a3c5d7f90
Create Date: 2026-07-17 15:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "7f2b4d6e8a10"
down_revision: Union[str, Sequence[str], None] = "6e1a3c5d7f90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEAD_INDEX_NAME = "uq_lead_bot_source_fingerprint"
RECOGNITION_INDEX_NAME = "uq_customer_requisites_telegram_message"
STAGE_INDEX_NAME = "uq_unassigned_order_work_stage_schedule"


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    duplicate_groups = op.get_bind().execute(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT source_fingerprint
                FROM lead
                WHERE source = 'bot' AND source_fingerprint IS NOT NULL
                GROUP BY source_fingerprint
                HAVING count(*) > 1
            ) duplicate_bot_fingerprints
            """
        )
    ).scalar_one()
    if duplicate_groups:
        raise RuntimeError(
            "Cannot enforce bot quick-order idempotency: duplicate bot lead fingerprints exist"
        )

    if LEAD_INDEX_NAME not in _indexes("lead"):
        op.create_index(
            LEAD_INDEX_NAME,
            "lead",
            ["source_fingerprint"],
            unique=True,
            postgresql_where=sa.text("source = 'bot' AND source_fingerprint IS NOT NULL"),
            sqlite_where=sa.text("source = 'bot' AND source_fingerprint IS NOT NULL"),
        )

    duplicate_recognitions = op.get_bind().execute(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT source, telegram_user_id, telegram_chat_id, telegram_message_id
                FROM customer_requisites_recognition
                WHERE source IN ('telegram', 'telegram_text')
                  AND telegram_user_id IS NOT NULL
                  AND telegram_chat_id IS NOT NULL
                  AND telegram_message_id IS NOT NULL
                GROUP BY source, telegram_user_id, telegram_chat_id, telegram_message_id
                HAVING count(*) > 1
            ) duplicate_telegram_recognitions
            """
        )
    ).scalar_one()
    if duplicate_recognitions:
        raise RuntimeError(
            "Cannot enforce requisites idempotency: duplicate Telegram recognitions exist"
        )

    if RECOGNITION_INDEX_NAME not in _indexes("customer_requisites_recognition"):
        predicate = sa.text(
            "source IN ('telegram', 'telegram_text') "
            "AND telegram_user_id IS NOT NULL "
            "AND telegram_chat_id IS NOT NULL "
            "AND telegram_message_id IS NOT NULL"
        )
        op.create_index(
            RECOGNITION_INDEX_NAME,
            "customer_requisites_recognition",
            ["source", "telegram_user_id", "telegram_chat_id", "telegram_message_id"],
            unique=True,
            postgresql_where=predicate,
            sqlite_where=predicate,
        )

    duplicate_stages = op.get_bind().execute(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT order_id, name, start_time
                FROM order_work_stage
                WHERE installer_id IS NULL AND start_time IS NOT NULL
                GROUP BY order_id, name, start_time
                HAVING count(*) > 1
            ) duplicate_unassigned_stages
            """
        )
    ).scalar_one()
    if duplicate_stages:
        raise RuntimeError(
            "Cannot enforce quick-order stage idempotency: duplicate unassigned stages exist"
        )

    if STAGE_INDEX_NAME not in _indexes("order_work_stage"):
        predicate = sa.text("installer_id IS NULL AND start_time IS NOT NULL")
        op.create_index(
            STAGE_INDEX_NAME,
            "order_work_stage",
            ["order_id", "name", "start_time"],
            unique=True,
            postgresql_where=predicate,
            sqlite_where=predicate,
        )


def downgrade() -> None:
    if STAGE_INDEX_NAME in _indexes("order_work_stage"):
        op.drop_index(STAGE_INDEX_NAME, table_name="order_work_stage")
    if RECOGNITION_INDEX_NAME in _indexes("customer_requisites_recognition"):
        op.drop_index(RECOGNITION_INDEX_NAME, table_name="customer_requisites_recognition")
    if LEAD_INDEX_NAME in _indexes("lead"):
        op.drop_index(LEAD_INDEX_NAME, table_name="lead")
