from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, Column, JSON, String, UniqueConstraint
from sqlmodel import Field, SQLModel


class StaffUser(SQLModel, table=True):
    __tablename__ = "staff_users"
    __table_args__ = (
        UniqueConstraint(
            "legacy_installer_id",
            name="uq_staff_users_legacy_installer_id",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    display_name: str = Field(index=True)
    status: str = Field(default="active", sa_column=Column(String, index=True, nullable=False))
    roles: List[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    primary_role: str = Field(default="installer", sa_column=Column(String, index=True, nullable=False))

    username: Optional[str] = Field(default=None, sa_column=Column(String, unique=True, nullable=True))
    password_hash: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))

    phone: Optional[str] = Field(default=None, index=True)
    email: Optional[str] = Field(default=None, index=True)
    telegram_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, unique=True, nullable=True))
    telegram_username: Optional[str] = Field(default=None, index=True)

    legacy_installer_id: Optional[int] = Field(
        default=None,
        foreign_key="installers.id",
        index=True,
    )
    default_rate: Optional[float] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.now)
    last_login_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )
