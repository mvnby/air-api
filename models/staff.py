from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, Column, JSON, String
from sqlmodel import Field, SQLModel


class StaffUser(SQLModel, table=True):
    __tablename__ = "staff_users"

    id: Optional[int] = Field(default=None, primary_key=True)
    display_name: str = Field(index=True)
    status: str = Field(default="active", sa_column=Column(String, index=True, nullable=False))
    roles: List[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))

    phone: Optional[str] = Field(default=None, index=True)
    email: Optional[str] = Field(default=None, index=True)
    telegram_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, unique=True, nullable=True))

    legacy_installer_id: Optional[int] = Field(default=None, foreign_key="installers.id", unique=True, index=True)
    default_rate: Optional[float] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )
