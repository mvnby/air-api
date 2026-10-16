"""Single-use company invitations; raw bearer tokens are never persisted."""
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, String, CheckConstraint
from sqlmodel import SQLModel, Field


class StaffInvitation(SQLModel, table=True):
    __tablename__ = "staff_invitation"
    __table_args__ = (CheckConstraint("role IN ('owner','admin','manager','catalog_editor')", name="ck_staff_invitation_role"),)
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    created_by_staff_user_id: int = Field(foreign_key="staff_users.id")
    accepted_by_staff_user_id: int | None = Field(default=None, foreign_key="staff_users.id")
    token_hash: str = Field(sa_column=Column(String(64), unique=True, nullable=False))
    role: str = Field(sa_column=Column(String(24), nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    accepted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    revoked_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
