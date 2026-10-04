from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, String, Text
from sqlmodel import Field, SQLModel


class DeepSeekConnection(SQLModel, table=True):
    """System credential; an empty row also retires the environment fallback."""

    __tablename__ = "deepseek_connection"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_deepseek_connection_singleton"),
        CheckConstraint(
            "(encrypted_credentials IS NULL) = (credentials_fingerprint IS NULL)",
            name="ck_deepseek_connection_credential_pair",
        ),
        CheckConstraint(
            "NOT enabled OR encrypted_credentials IS NOT NULL",
            name="ck_deepseek_connection_enabled_key",
        ),
    )

    id: int = Field(default=1, primary_key=True)
    encrypted_credentials: str | None = Field(default=None, sa_column=Column(Text))
    credentials_fingerprint: str | None = Field(default=None, sa_column=Column(String(64)))
    enabled: bool = Field(default=False, nullable=False)
