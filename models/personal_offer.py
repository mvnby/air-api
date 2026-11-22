from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKeyConstraint, Index, JSON, String, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel

from models.tenancy import utc_now


class PersonalOffer(SQLModel, table=True):
    __tablename__ = "personal_offer"
    __table_args__ = (
        ForeignKeyConstraint(
            ("storefront_id", "tenant_id"), ("storefront.id", "storefront.tenant_id"),
            name="fk_personal_offer_storefront_scope",
        ),
        Index("ix_personal_offer_scope", "tenant_id", "storefront_id", "id"),
        Index("ix_personal_offer_order_scope", "tenant_id", "storefront_id", "order_id", "id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id")
    storefront_id: int
    order_id: int | None = Field(default=None, foreign_key="order.id", ondelete="SET NULL")
    version: int = Field(default=1)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    rooms: list[dict] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class PersonalOfferPublication(SQLModel, table=True):
    __tablename__ = "personal_offer_publication"
    __table_args__ = (
        UniqueConstraint("offer_id", "request_id", name="uq_personal_offer_publication_receipt"),
        UniqueConstraint("token_digest", name="uq_personal_offer_publication_token_digest"),
        Index(
            "uq_personal_offer_current_publication", "offer_id", unique=True,
            postgresql_where=text("revoked_at IS NULL"), sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    offer_id: int = Field(foreign_key="personal_offer.id", ondelete="CASCADE")
    request_id: str = Field(sa_column=Column(String(36), nullable=False))
    draft_version: int
    token_digest: str = Field(sa_column=Column(String(64), nullable=False))
    encrypted_token: str = Field(sa_column=Column(Text, nullable=False))
    hostname: str = Field(sa_column=Column(String(253), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    snapshot: dict = Field(sa_column=Column(JSON, nullable=False))
    published_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    revoked_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
