from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, Index, String
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BotVoiceTranscriptionAudit(SQLModel, table=True):
    __tablename__ = "bot_voice_transcription_audit"
    __table_args__ = (
        Index(
            "ix_bot_voice_audit_telegram_message",
            "telegram_user_id",
            "telegram_chat_id",
            "telegram_message_id",
        ),
        CheckConstraint(
            "status IN ('processing', 'completed', 'failed')",
            name="ck_bot_voice_audit_status",
        ),
    )

    audit_id: str = Field(sa_column=Column(String(32), primary_key=True))
    telegram_user_id: int = Field(
        sa_column=Column(BigInteger, nullable=False, index=True)
    )
    telegram_chat_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    telegram_message_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    status: str = Field(sa_column=Column(String(24), nullable=False, index=True))
    filename: str = Field(sa_column=Column(String(160), nullable=False))
    mime_type: str = Field(sa_column=Column(String(80), nullable=False))
    size_bytes: int
    duration_seconds: int
    detected_duration_ms: int
    request_sha256: str = Field(sa_column=Column(String(64), nullable=False))
    provider: str = Field(sa_column=Column(String(40), nullable=False))
    model: str = Field(sa_column=Column(String(120), nullable=False))
    transcript_length: Optional[int] = None
    transcript_sha256: Optional[str] = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
    )
    error_code: Optional[str] = Field(
        default=None,
        sa_column=Column(String(80), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
