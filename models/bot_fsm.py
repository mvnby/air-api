from datetime import datetime
from typing import Optional

from sqlalchemy import Column, JSON, String
from sqlmodel import Field, SQLModel


class BotFsmState(SQLModel, table=True):
    __tablename__ = "bot_fsm_state"

    storage_key: str = Field(primary_key=True)
    bot_id: int = Field(index=True)
    chat_id: int = Field(index=True)
    user_id: int = Field(index=True)
    thread_id: Optional[int] = Field(default=None, index=True)
    business_connection_id: Optional[str] = Field(default=None, index=True)
    destiny: str = Field(default="default", sa_column=Column(String, index=True, nullable=False))
    state: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    data: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False, default=dict))
    updated_at: datetime = Field(default_factory=datetime.now, index=True, sa_column_kwargs={"onupdate": datetime.now})


class BotRuntimeLease(SQLModel, table=True):
    """Short-lived ownership lease for an independently deployed bot process."""

    __tablename__ = "bot_runtime_lease"

    name: str = Field(primary_key=True)
    owner_id: str = Field(index=True, max_length=160)
    expires_at: datetime = Field(index=True)
    updated_at: datetime = Field(default_factory=datetime.now, index=True)
