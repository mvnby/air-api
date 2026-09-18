"""Durable cursor state for the Belzakupki opportunities importer."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BelzakupkiImportCheckpoint(SQLModel, table=True):
    """One opaque remote cursor for one explicitly configured storefront."""

    __tablename__ = "belzakupki_import_checkpoint"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "storefront_id",
            name="uq_belzakupki_import_checkpoint_scope",
        ),
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_belzakupki_import_checkpoint_storefront_tenant",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    storefront_id: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    cursor: str | None = Field(default=None, sa_column=Column(String(2048), nullable=True))
    updated_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
