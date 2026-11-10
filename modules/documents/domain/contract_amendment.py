"""Typed additional work; never an order-proposal edit or performance statement."""

from decimal import Decimal, ROUND_HALF_UP
from pydantic import BaseModel, ConfigDict, Field, model_validator

TYPE = "contract_amendment"
BASIS_TYPES = frozenset({"contract", "b2c_supply_installation_act"})
ACTIVE_STATUSES = ("issued", "sent", "signed")


class AmendmentWork(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=1500)
    quantity: Decimal = Field(gt=0, le=1000000, decimal_places=3)
    unit: str = Field(min_length=1, max_length=40)
    unit_price: Decimal = Field(gt=0, le=100000000, decimal_places=2)


class ContractAmendmentTerms(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    works: list[AmendmentWork] = Field(min_length=1, max_length=100)
    equipment: str = Field(default="", max_length=2000)
    acceptance_terms: str = Field(
        default="Приёмка дополнительных работ производится на условиях исходного договора.",
        min_length=1,
        max_length=4000,
    )
    payment_terms: str = Field(
        default="Оплата дополнительных работ производится на условиях исходного договора.",
        min_length=1,
        max_length=4000,
    )
    effective_terms: str = Field(
        default="Настоящее соглашение вступает в силу после подписания обеими сторонами.",
        min_length=1,
        max_length=4000,
    )

    @model_validator(mode="after")
    def positive_amount(self):
        if self.amount <= 0:
            raise ValueError("Сумма дополнительных работ должна быть больше нуля")
        return self

    @property
    def amount(self) -> Decimal:
        return sum(
            (
                (w.quantity * w.unit_price).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                for w in self.works
            ),
            Decimal("0.00"),
        )
