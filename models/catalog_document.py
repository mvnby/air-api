"""Technical/research material attached to the shared equipment catalog."""

from datetime import datetime

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel


class CatalogDocument(SQLModel, table=True):
    __tablename__ = "catalog_document"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN brand_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN series_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN product_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_catalog_document_one_owner",
        ),
        CheckConstraint("visibility IN ('public', 'internal')", name="ck_catalog_document_visibility"),
        CheckConstraint(
            "kind IN ('catalog', 'operation', 'installation', 'service', 'brochure', 'certificate', 'other')",
            name="ck_catalog_document_kind",
        ),
        CheckConstraint("length(trim(title)) > 0", name="ck_catalog_document_title"),
        CheckConstraint("year IS NULL OR year BETWEEN 1900 AND 2200", name="ck_catalog_document_year"),
        UniqueConstraint("brand_id", "url", name="uq_catalog_document_brand_url"),
        UniqueConstraint("series_id", "url", name="uq_catalog_document_series_url"),
        UniqueConstraint("product_id", "url", name="uq_catalog_document_product_url"),
    )

    id: int | None = Field(default=None, primary_key=True)
    brand_id: int | None = Field(default=None, foreign_key="brand.id", ondelete="CASCADE", index=True)
    series_id: int | None = Field(default=None, foreign_key="product_series.id", ondelete="CASCADE", index=True)
    product_id: int | None = Field(default=None, foreign_key="product.id", ondelete="CASCADE", index=True)
    kind: str = Field(default="other", max_length=24)
    title: str = Field(max_length=250)
    url: str = Field(max_length=2048)
    source_url: str | None = Field(default=None, max_length=2048)
    language: str | None = Field(default=None, max_length=16)
    year: int | None = None
    visibility: str = Field(default="public", max_length=16)
    inherit_to_products: bool = Field(default=True)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
