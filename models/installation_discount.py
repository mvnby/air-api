from datetime import datetime

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


class InstallationDiscountPolicy(SQLModel, table=True):
    """Singleton policy for catalog-product installation discounts."""

    __tablename__ = "installation_discount_policy"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_installation_discount_policy_singleton"),
        CheckConstraint(
            "default_discount BETWEEN 0 AND 10000",
            name="ck_installation_discount_policy_default_discount",
        ),
        CheckConstraint(
            "minimum_margin BETWEEN 0 AND 1000000",
            name="ck_installation_discount_policy_minimum_margin",
        ),
    )

    id: int = Field(default=1, primary_key=True)
    is_enabled: bool = Field(default=False)
    default_discount: int = Field(default=100)
    minimum_margin: int = Field(default=350)
    updated_at: datetime = Field(default_factory=datetime.now)


class InstallationDiscountProductRule(SQLModel, table=True):
    """Explicit per-product amount; zero means the discount is disabled."""

    __tablename__ = "installation_discount_product_rule"
    __table_args__ = (
        CheckConstraint(
            "discount_amount BETWEEN 0 AND 10000",
            name="ck_installation_discount_product_rule_amount",
        ),
    )

    product_id: int = Field(
        foreign_key="product.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    discount_amount: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
