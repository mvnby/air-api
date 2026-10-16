"""Short-lived, browser-bound Telegram account linking and login challenges."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Column, DateTime, String
from sqlmodel import Field, SQLModel


class StaffTelegramChallenge(SQLModel, table=True):
    __tablename__ = "staff_telegram_challenge"

    id: str = Field(primary_key=True, max_length=32)
    purpose: str = Field(max_length=16, index=True)
    token_hash: str = Field(max_length=64, unique=True)
    browser_hash: str = Field(max_length=64)
    status: str = Field(default="pending", max_length=24)
    staff_user_id: Optional[int] = Field(default=None, foreign_key="staff_users.id", index=True)
    auth_version: Optional[int] = None
    previous_telegram_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    telegram_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    telegram_username: Optional[str] = Field(default=None, max_length=160)
    telegram_display_name: Optional[str] = Field(default=None, max_length=300)
    browser_code: Optional[str] = Field(default=None, max_length=8)
    claim_key: Optional[str] = Field(default=None, max_length=100)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    consumed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


class StaffTelegramWidgetReceipt(SQLModel, table=True):
    __tablename__ = "staff_telegram_widget_receipt"

    signature_hash: str = Field(primary_key=True, max_length=64)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class StaffTelegramRetiredIdentity(SQLModel, table=True):
    """Historical proof that a Telegram ID is no longer an unknown legacy ID."""

    __tablename__ = "staff_telegram_retired_identity"

    telegram_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    staff_user_id: int = Field(foreign_key="staff_users.id", index=True)
    retired_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc),
                                 sa_column=Column(DateTime(timezone=True), nullable=False))
