from __future__ import annotations

from typing import Optional

from sqlalchemy import CheckConstraint, Column, String, Text
from sqlmodel import Field, SQLModel


class PlatformAIConnection(SQLModel, table=True):
    """One system-owned credential; never joined to a partner tenant."""

    __tablename__ = "platform_ai_connection"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_platform_ai_connection_singleton"),
    )

    id: Optional[int] = Field(default=1, primary_key=True)
    encrypted_credentials: str = Field(sa_column=Column(Text, nullable=False))
    credentials_fingerprint: str = Field(sa_column=Column(String(64), nullable=False))
    enabled: bool = Field(default=False, nullable=False)
    selected_model: Optional[str] = Field(default=None, sa_column=Column(String(160)))
