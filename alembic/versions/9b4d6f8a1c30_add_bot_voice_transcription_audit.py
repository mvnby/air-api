"""add bot voice transcription audit

Revision ID: 9b4d6f8a1c30
Revises: 8a3c5e7f9b21
Create Date: 2026-07-18 13:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "9b4d6f8a1c30"
down_revision: Union[str, Sequence[str], None] = "8a3c5e7f9b21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "bot_voice_transcription_audit" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "bot_voice_transcription_audit",
        sa.Column("audit_id", sa.String(length=32), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("filename", sa.String(length=160), nullable=False),
        sa.Column("mime_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("detected_duration_ms", sa.Integer(), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("transcript_length", sa.Integer(), nullable=True),
        sa.Column("transcript_sha256", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('processing', 'completed', 'failed')",
            name="ck_bot_voice_audit_status",
        ),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index(
        "ix_bot_voice_transcription_audit_telegram_user_id",
        "bot_voice_transcription_audit",
        ["telegram_user_id"],
    )
    op.create_index(
        "ix_bot_voice_transcription_audit_status",
        "bot_voice_transcription_audit",
        ["status"],
    )
    op.create_index(
        "ix_bot_voice_transcription_audit_created_at",
        "bot_voice_transcription_audit",
        ["created_at"],
    )
    op.create_index(
        "ix_bot_voice_audit_telegram_message",
        "bot_voice_transcription_audit",
        ["telegram_user_id", "telegram_chat_id", "telegram_message_id"],
    )


def downgrade() -> None:
    if "bot_voice_transcription_audit" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("bot_voice_transcription_audit")
