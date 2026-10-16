from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, LargeBinary, String
from sqlmodel import Field, SQLModel


class StaffAvatar(SQLModel, table=True):
    """Small sanitized photos, delivered through authenticated company access."""

    __tablename__ = "staff_avatar"

    staff_user_id: int = Field(primary_key=True, foreign_key="staff_users.id")
    content: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    content_hash: str = Field(sa_column=Column(String(64), nullable=False))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
