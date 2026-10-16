"""Durable selection; version never resets when returning to the default site."""

from sqlalchemy import CheckConstraint, ForeignKeyConstraint
from sqlmodel import Field, SQLModel


class BotStaffSelection(SQLModel, table=True):
    __tablename__ = "bot_staff_selection"
    __table_args__ = (
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"], ["storefront.id", "storefront.tenant_id"]
        ),
        CheckConstraint("context_version >= 0", name="ck_bot_staff_selection_version"),
    )
    staff_user_id: int = Field(primary_key=True, foreign_key="staff_users.id")
    tenant_id: int = Field(foreign_key="tenant.id")
    storefront_id: int
    context_version: int = Field(default=0)
