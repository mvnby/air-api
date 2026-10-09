"""Manual tender business context; source records retain independent identities."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKeyConstraint, Index, String
from sqlmodel import Field, SQLModel


class TenderWorkflowContext(SQLModel, table=True):
    __tablename__ = "tender_workflow_context"
    __table_args__ = (
        ForeignKeyConstraint(["order_id", "tenant_id", "storefront_id"],
            ["order.id", "order.tenant_id", "order.storefront_id"], ondelete="CASCADE"),
        CheckConstraint("stage IN ('price_request','price_sent','announced','submitted','completed')",
            name="ck_tender_workflow_stage"),
    )
    order_id: int = Field(primary_key=True)
    tenant_id: int
    storefront_id: int
    stage: str = Field(sa_column=Column(String(24), nullable=False))
    deadline_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    # Explicit null means no current deadline; false falls back to the source deadline.
    deadline_manual: bool = Field(default=False)


class TenderWorkflowLink(SQLModel, table=True):
    __tablename__ = "tender_workflow_link"
    __table_args__ = (
        ForeignKeyConstraint(["publication_order_id", "tenant_id", "storefront_id"],
            ["order.id", "order.tenant_id", "order.storefront_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["price_order_id", "tenant_id", "storefront_id"],
            ["order.id", "order.tenant_id", "order.storefront_id"], ondelete="CASCADE"),
        CheckConstraint("publication_order_id <> price_order_id", name="ck_tender_workflow_distinct"),
        Index("ix_tender_workflow_price_scope", "price_order_id", "tenant_id", "storefront_id"),
    )
    publication_order_id: int = Field(primary_key=True)
    price_order_id: int
    tenant_id: int
    storefront_id: int
